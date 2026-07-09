"""
Inbox watcher: with the user's explicit consent (Options → Inbox watcher),
JobBot reads their OWN mailbox over read-only IMAP and reacts to job-search
email so they don't have to bookkeep by hand:

  - application confirmation  -> mark that job Applied automatically
  - interview / offer         -> ping them right away (Telegram, else email)
  - rejection                 -> ping them (no status is changed — "rejected"
                                 in JobBot means the USER declined a match)

Privacy rules:
  - IMAP is opened READ-ONLY; JobBot never sends, moves, or deletes mail.
  - Most messages are only ever seen as headers: a keyword prefilter decides
    which few look job-related, and only those have a short text snippet read
    and classified by the AI.
  - Nothing from the mailbox is stored except the subject + message-id of the
    handful of ACTIONABLE messages (the inbox_events audit trail).
  - The IMAP password is Fernet-encrypted with a key derived from SECRET_KEY.

Runs inside the normal scheduler cycle (app/runner.py) and via
`python manage.py scan-inbox`. Incremental: only messages newer than the last
scanned UID are ever fetched.
"""

from __future__ import annotations

import base64
import email
import email.header
import hashlib
import imaplib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as SessionType

from app.config import settings
from app.models import ApplicationKit, InboxEvent, Job, Match, Star, User

logger = logging.getLogger("jobbot.inbox")

# How far back the FIRST scan looks (later scans are incremental by UID).
FIRST_SCAN_DAYS = 3
# Per-scan caps: newest N messages considered, M classified, P pings sent.
MAX_NEW = 40
MAX_CLASSIFY = 15
MAX_PINGS = 5
MAX_MSG_BYTES = 300_000
SNIPPET_CHARS = 2000

# Cheap header prefilter — only messages matching this ever have a body read.
_JOBMAIL = re.compile(
    r"applic|interview|candidat|recruit|hiring|talent|position|role|resume|"
    r"offer|assessment|screening|unfortunately|regret|next steps|onboard|"
    r"greenhouse|lever\.co|ashby|workday|icims|taleo|indeed|ziprecruiter|"
    r"linkedin|jobvite|smartrecruiters",
    re.I,
)

KINDS = {"application_confirmation", "rejection", "interview", "offer"}


# ---------------------------------------------------------------- credentials
def _fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(
        (settings.secret_key or "dev-insecure-change-me").encode() + b"jobbot-inbox"
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal(plain: str) -> str:
    """Encrypt an IMAP password for storage."""
    return _fernet().encrypt((plain or "").encode()).decode()


def unseal(token: str) -> str:
    """Decrypt a stored IMAP password ('' when the token is bad/absent)."""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception:  # noqa: BLE001 — a bad token just means "not connected"
        return ""


# ------------------------------------------------------------------- plumbing
def _connect(host: str, addr: str, password: str) -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL(host, 993, timeout=25)
    imap.login(addr, password)
    imap.select("INBOX", readonly=True)  # read-only: we can never change mail
    return imap


def test_connection(host: str, addr: str, password: str) -> tuple[bool, str]:
    """Try a real login+select; (ok, error-for-humans)."""
    try:
        imap = _connect((host or "imap.gmail.com").strip(), addr.strip(), password)
        imap.logout()
        return True, ""
    except imaplib.IMAP4.error as exc:
        return False, f"The mail server refused the login: {exc}"
    except OSError as exc:
        return False, f"Couldn't reach the mail server: {exc}"


def _new_uids(imap: imaplib.IMAP4_SSL, last_uid: int | None) -> list[int]:
    if last_uid:
        # NB: "UID N:*" always matches at least the mailbox's last message,
        # even when its uid <= N — so filter, don't trust the range.
        _typ, data = imap.uid("search", None, f"UID {last_uid + 1}:*")
        uids = [int(u) for u in (data[0] or b"").split()]
        uids = [u for u in uids if u > last_uid]
    else:
        since = (datetime.now(timezone.utc) - timedelta(days=FIRST_SCAN_DAYS))
        _typ, data = imap.uid("search", None, f'(SINCE "{since.strftime("%d-%b-%Y")}")')
        uids = [int(u) for u in (data[0] or b"").split()]
    return sorted(uids)[-MAX_NEW:]


def _decode_hdr(raw: str) -> str:
    try:
        parts = email.header.decode_header(raw)
        out = []
        for text, enc in parts:
            if isinstance(text, bytes):
                out.append(text.decode(enc or "utf-8", errors="replace"))
            else:
                out.append(text)
        return "".join(out).strip()
    except Exception:  # noqa: BLE001
        return (raw or "").strip()


def _headers(imap: imaplib.IMAP4_SSL, uid: int) -> dict | None:
    _typ, data = imap.uid(
        "fetch", str(uid),
        "(RFC822.SIZE BODY.PEEK[HEADER.FIELDS (SUBJECT FROM MESSAGE-ID)])",
    )
    blob, meta = None, b""
    for part in data or []:
        if isinstance(part, tuple) and len(part) == 2:
            meta, blob = part[0] or b"", part[1] or b""
    if blob is None:
        return None
    msg = email.message_from_bytes(blob)
    m = re.search(rb"RFC822\.SIZE (\d+)", meta)
    return {
        "uid": uid,
        "subject": _decode_hdr(msg.get("Subject", "")),
        "from": _decode_hdr(msg.get("From", "")),
        "message_id": (msg.get("Message-ID") or f"<uid-{uid}>").strip()[:255],
        "size": int(m.group(1)) if m else 0,
    }


def _snippet(imap: imaplib.IMAP4_SSL, uid: int) -> str:
    """First ~2000 chars of the message text (plain part preferred)."""
    _typ, data = imap.uid("fetch", str(uid), "(BODY.PEEK[])")
    blob = None
    for part in data or []:
        if isinstance(part, tuple) and len(part) == 2:
            blob = part[1]
    if not blob:
        return ""
    msg = email.message_from_bytes(blob)
    plain, html = "", ""
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True) or b""
            text = payload.decode(part.get_content_charset() or "utf-8",
                                  errors="replace")
        except Exception:  # noqa: BLE001
            continue
        if ctype == "text/plain" and not plain:
            plain = text
        elif ctype == "text/html" and not html:
            html = text
    body = plain or re.sub(r"<[^>]+>", " ", html)
    body = re.sub(r"\s+", " ", body).strip()
    return body[:SNIPPET_CHARS]


# -------------------------------------------------------------- classification
def _classify(candidates: list[dict]) -> list[dict]:
    """One batched AI call: label each candidate email. Returns [] on failure."""
    from app.llm import LLMError, get_default_provider

    system = (
        "You label a job seeker's incoming emails. For EACH numbered email, "
        "decide what it is FOR THE CANDIDATE'S OWN job applications:\n"
        '- "application_confirmation": an employer/ATS confirming THE CANDIDATE '
        "applied (e.g. 'thanks for applying', 'application received').\n"
        '- "rejection": the employer is declining/passing on the candidate.\n'
        '- "interview": the employer wants to schedule a call/interview/'
        "assessment next step.\n"
        '- "offer": a job offer.\n'
        '- "other": ANYTHING else — job ads, alerts/digests, newsletters, '
        "recruiter cold spam, receipts. When unsure, use \"other\".\n"
        "Reply with a single JSON object: "
        '{"emails": [{"i": <number>, "kind": "<label>", '
        '"company": "<employer name or \'\'>", "role": "<job title or \'\'>"}]}'
    )
    lines = []
    for n, c in enumerate(candidates):
        lines.append(
            f"--- EMAIL {n} ---\nFrom: {c['from'][:200]}\n"
            f"Subject: {c['subject'][:300]}\nBody: {c.get('snippet', '')[:1500]}"
        )
    try:
        raw = get_default_provider().complete(
            system, "\n\n".join(lines), json_mode=True,
            max_output_tokens=900, temperature=0.0,
        )
        data = json.loads(raw)
    except (LLMError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("inbox classification failed: %s", exc)
        return []
    out = []
    for row in (data.get("emails") if isinstance(data, dict) else None) or []:
        if not isinstance(row, dict):
            continue
        try:
            i = int(row.get("i"))
        except (TypeError, ValueError):
            continue
        kind = str(row.get("kind") or "other").strip().lower()
        if 0 <= i < len(candidates) and kind in KINDS:
            out.append({
                "i": i, "kind": kind,
                "company": str(row.get("company") or "").strip()[:120],
                "role": str(row.get("role") or "").strip()[:150],
            })
    return out


# ------------------------------------------------------------------- matching
_CO_NOISE = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|group)\b\.?", re.I)


def _norm_co(name: str) -> str:
    name = _CO_NOISE.sub(" ", (name or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", name).strip()


def _match_job(session: SessionType, user: User, company: str, role: str) -> Job | None:
    """Find which of the user's JobBot jobs an email is about — by company name,
    with the role as a tie-break. Starred jobs first (most likely applied),
    then kit jobs, then matches by score."""
    target = _norm_co(company)
    if len(target) < 3:
        return None

    seen: set[int] = set()
    ordered: list[Job] = []

    def _add(job: Job | None) -> None:
        if job is not None and job.id not in seen:
            seen.add(job.id)
            ordered.append(job)

    for star in (session.query(Star).filter_by(user_id=user.id)
                 .order_by(Star.created_at.desc()).all()):
        _add(session.get(Job, star.job_id))
    for kit in session.query(ApplicationKit).filter_by(user_id=user.id).all():
        _add(session.get(Job, kit.job_id))
    for m, j in (session.query(Match, Job).join(Job, Match.job_id == Job.id)
                 .filter(Match.user_id == user.id)
                 .order_by(Match.score.desc()).limit(300).all()):
        _add(j)

    role_l = (role or "").lower()
    best = None
    for job in ordered:
        co = _norm_co(job.company or "")
        if len(co) < 3:
            continue
        if target in co or co in target:
            if best is None:
                best = job
            # a role-title overlap beats plain company order
            if role_l and job.title and role_l[:25] in job.title.lower():
                return job
    return best


# --------------------------------------------------------------------- pinging
def guess_imap_host(email_addr: str) -> str:
    """The IMAP server for common providers, so users never have to know it.
    Unknown domains get the conventional imap.<domain> guess (the connect flow
    verifies with a real login before saving, so a wrong guess just errors)."""
    domain = (email_addr or "").rsplit("@", 1)[-1].strip().lower()
    known = {
        "gmail.com": "imap.gmail.com",
        "googlemail.com": "imap.gmail.com",
        "outlook.com": "outlook.office365.com",
        "hotmail.com": "outlook.office365.com",
        "live.com": "outlook.office365.com",
        "msn.com": "outlook.office365.com",
        "yahoo.com": "imap.mail.yahoo.com",
        "ymail.com": "imap.mail.yahoo.com",
        "icloud.com": "imap.mail.me.com",
        "me.com": "imap.mail.me.com",
        "mac.com": "imap.mail.me.com",
        "aol.com": "imap.aol.com",
    }
    return known.get(domain, f"imap.{domain}" if domain else "imap.gmail.com")


PING_CHANNELS = ("telegram", "email", "ntfy", "discord")


def _ping(user: User, html: str, text: str) -> bool:
    """Deliver one inbox-watcher ping over every channel the user picked
    (Options → Inbox watcher). No selection stored = the original default:
    Telegram when connected, else email. True when ANY channel delivered."""
    from app.alerts.discord import send_discord
    from app.alerts.email import send_email
    from app.alerts.ntfy import send_ntfy
    from app.alerts.telegram import send_telegram

    channels = [c for c in (user.inbox_ping_channels or []) if c in PING_CHANNELS]
    if not channels:  # default behavior (pre-feature rows / nothing picked)
        if user.telegram_chat_id and send_telegram(user.telegram_chat_id, html):
            return True
        return send_email(user.email,
                          "JobBot — an update on one of your applications",
                          text, f"<p>{html}</p>").ok

    delivered = False
    if "telegram" in channels and user.telegram_chat_id:
        delivered |= send_telegram(user.telegram_chat_id, html)
    if "email" in channels:
        delivered |= send_email(user.email,
                                "JobBot — an update on one of your applications",
                                text, f"<p>{html}</p>").ok
    if "ntfy" in channels and user.ntfy_topic:
        delivered |= send_ntfy(user.ntfy_topic, "JobBot", text)
    if "discord" in channels and user.discord_webhook:
        delivered |= send_discord(user.discord_webhook, text)
    return delivered


@dataclass
class InboxReport:
    email: str
    scanned: int = 0
    candidates: int = 0
    events: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


# ------------------------------------------------------------------ main scan
def scan_user_inbox(session: SessionType, user: User) -> InboxReport:
    report = InboxReport(email=user.email)
    if not user.inbox_enabled:
        report.skipped_reason = "inbox watcher not enabled"
        return report
    password = unseal(user.imap_password or "")
    if not (user.imap_email and password):
        report.skipped_reason = "no mailbox credentials"
        return report

    base = settings.app_base_url.rstrip("/")
    imap = _connect((user.imap_host or "imap.gmail.com").strip(),
                    user.imap_email.strip(), password)
    try:
        uids = _new_uids(imap, user.inbox_last_uid)
        report.scanned = len(uids)

        candidates: list[dict] = []
        for uid in uids:
            head = _headers(imap, uid)
            if head is None or head["size"] > MAX_MSG_BYTES:
                continue
            if _JOBMAIL.search(f"{head['subject']} {head['from']}"):
                candidates.append(head)
        candidates = candidates[-MAX_CLASSIFY:]
        for c in candidates:
            c["snippet"] = _snippet(imap, c["uid"])
        report.candidates = len(candidates)

        labeled: list[dict] = []
        if candidates:
            from app.llm_budget import try_spend

            if settings.llm_configured and try_spend(session, 1):
                labeled = _classify(candidates)
            else:
                logger.info("inbox %s: %d candidates but no AI budget — skipped",
                            user.email, len(candidates))

        pings = 0
        for row in labeled:
            cand = candidates[row["i"]]
            # never act on the same message twice (survives cursor resets)
            dup = (session.query(InboxEvent)
                   .filter_by(user_id=user.id, message_id=cand["message_id"]).first())
            if dup is not None:
                continue

            job = _match_job(session, user, row["company"], row["role"])
            kind = row["kind"]
            label = row["company"] or "an employer"
            role = row["role"] or (job.title if job else "a role")
            link = f'<a href="{base}/jobs/{job.id}">{job.title}</a>' if job else role

            html = text = None
            if kind == "application_confirmation":
                if job is not None:
                    star = (session.query(Star)
                            .filter_by(user_id=user.id, job_id=job.id).first())
                    if star is None:
                        star = Star(user_id=user.id, job_id=job.id)
                        session.add(star)
                    if star.status != "applied":
                        star.status = "applied"
                        star.created_at = datetime.now(timezone.utc)
                        html = (f"✅ Marked {link} @ {job.company or label} as "
                                f"<b>applied</b> — saw your confirmation email.")
                        text = (f"Marked {job.title} @ {job.company or label} as "
                                "applied — saw your confirmation email.")
            elif kind in ("interview", "offer"):
                nice = "🎉 Interview request" if kind == "interview" else "🎊 Job offer"
                html = (f"{nice} — {link} @ {label}.<br>"
                        f"Email subject: “{cand['subject'][:150]}”")
                text = (f"{nice.split(' ', 1)[1].capitalize()} — {role} @ {label}. "
                        f"Email subject: {cand['subject'][:150]}")
            elif kind == "rejection":
                html = (f"📩 Looks like a rejection for {link} @ {label}. "
                        "Keep going — new matches land daily. 💪")
                text = (f"Looks like a rejection for {role} @ {label}. "
                        "Keep going — new matches land daily.")

            if html and pings < MAX_PINGS:
                if _ping(user, html, text or ""):
                    pings += 1
            if html or kind == "application_confirmation":
                session.add(InboxEvent(
                    user_id=user.id, message_id=cand["message_id"], kind=kind,
                    job_id=job.id if job else None,
                    subject=cand["subject"][:300],
                ))
                report.events.append(
                    f"{kind}: {row['company'] or cand['subject'][:40]}"
                )

        if uids:
            user.inbox_last_uid = max(uids)
        user.inbox_scanned_at = datetime.now(timezone.utc)
        session.commit()
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass
    return report


def run_inbox_scans(session: SessionType) -> list[InboxReport]:
    """Scan every opted-in user. One user's failure never blocks the others."""
    reports: list[InboxReport] = []
    for user in session.query(User).filter_by(inbox_enabled=True).all():
        try:
            reports.append(scan_user_inbox(session, user))
        except Exception as exc:  # noqa: BLE001 — isolate per user
            logger.warning("inbox scan for %s failed: %s", user.email, exc)
            session.rollback()
            reports.append(InboxReport(email=user.email,
                                       skipped_reason=f"error: {exc}"))
    return reports
