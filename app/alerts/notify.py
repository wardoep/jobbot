"""
Decide what to send each user, then send it.

A "new match" = a Match row we haven't notified about yet (notified_at IS NULL)
whose score is at or above the user's CURRENT threshold. We respect their:
  - alert_channels : which of email / slack / dashboard they ticked
  - digest_mode    : "instant" (send every cycle) vs "digest" (at most once per
                     DIGEST_INTERVAL_HOURS, default daily)

After at least one channel delivers, we stamp notified_at on those matches so
the same job is never alerted twice (spec section 11). The "dashboard" channel
needs no send — those matches simply appear on the dashboard already.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session as SessionType

from app.alerts.compose import compose as build_message
from app.alerts.email import send_email
from app.alerts.slack import send_slack
from app.alerts.telegram import send_telegram
from app.config import settings
from app.models import ApplicationKit, Job, Match, User

logger = logging.getLogger("jobbot.alerts")


@dataclass
class UserAlertReport:
    email: str
    sent: bool = False
    channels: list[str] = field(default_factory=list)
    match_count: int = 0
    skipped_reason: Optional[str] = None


def _pending_matches(session: SessionType, user: User) -> list[tuple[Match, Job]]:
    """The user's un-notified matches at/above their threshold, best first."""
    threshold = (user.preferences.match_threshold if user.preferences else 0) or 0
    return (
        session.query(Match, Job)
        .join(Job, Match.job_id == Job.id)
        .filter(
            Match.user_id == user.id,
            Match.notified_at.is_(None),
            Match.score >= threshold,
        )
        .order_by(Match.score.desc())
        .all()
    )


def _digest_due(prefs, now: datetime) -> bool:
    """True if a digest user is allowed another digest yet (≥ interval since last)."""
    last = prefs.last_digest_at
    if last is None:
        return True
    if last.tzinfo is None:  # SQLite hands back naive datetimes
        last = last.replace(tzinfo=timezone.utc)
    return now - last >= timedelta(hours=settings.digest_interval_hours)


def _telegram_text(
    session: SessionType, user: User, pairs: list[tuple[Match, Job]], digest: bool
) -> str:
    """The Telegram message: a compact, linked briefing of the new matches,
    flagging jobs whose Application Kit is already built (✨ kit ready)."""
    base = settings.app_base_url.rstrip("/")
    kit_ids = {
        k.job_id
        for k in session.query(ApplicationKit.job_id).filter_by(user_id=user.id)
    }
    n = len(pairs)
    head = (
        f"🌅 <b>Your JobBot briefing</b> — {n} new match{'es' if n != 1 else ''}"
        if digest
        else f"⚡ <b>{n} new match{'es' if n != 1 else ''} just landed</b>"
    )
    lines = [head, ""]
    for m, j in pairs[:6]:
        bits = [f"<b>{m.score:.0f}</b> · <a href=\"{base}/jobs/{j.id}\">{j.title}</a>"]
        if j.company:
            bits.append(f"— {j.company}")
        if j.salary:
            bits.append(f"· ${j.salary:,}")
        if j.id in kit_ids:
            bits.append("· ✨ kit ready")
        lines.append(" ".join(bits))
    if n > 6:
        lines.append(f"…and {n - 6} more.")
    lines.append("")
    lines.append(f'<a href="{base}/matches">Open your matches →</a>')
    return "\n".join(lines)


def send_user_alerts(
    session: SessionType,
    user: User,
    *,
    force_digest: bool = False,
    now: Optional[datetime] = None,
) -> UserAlertReport:
    now = now or datetime.now(timezone.utc)
    report = UserAlertReport(email=user.email)

    prefs = user.preferences
    channels = set((prefs.alert_channels if prefs else None) or [])
    push = channels & {"email", "slack", "telegram"}
    if not push:
        report.skipped_reason = "no email/slack/telegram channel enabled"
        return report

    pairs = _pending_matches(session, user)
    report.match_count = len(pairs)
    if not pairs:  # never spam an empty alert (spec section 11)
        report.skipped_reason = "no new matches"
        return report

    digest = (prefs.digest_mode or "digest") == "digest"
    if digest and not force_digest and not _digest_due(prefs, now):
        report.skipped_reason = "digest already sent recently"
        return report

    msg = build_message(user, pairs, digest=digest)

    delivered: list[str] = []
    if "email" in push:
        res = send_email(user.email, msg.subject, msg.text, msg.html)
        if res.ok:
            delivered.append(f"email:{res.transport}")
    if "slack" in push:
        if prefs.slack_webhook:
            if send_slack(prefs.slack_webhook, msg.slack):
                delivered.append("slack")
        else:
            logger.info("user %s enabled Slack but has no webhook set", user.email)
    if "telegram" in push:
        if user.telegram_chat_id:
            if send_telegram(user.telegram_chat_id, _telegram_text(session, user, pairs, digest)):
                delivered.append("telegram")
        else:
            logger.info("user %s enabled Telegram but hasn't connected it", user.email)

    if not delivered:
        report.skipped_reason = "all enabled channels failed or unconfigured"
        return report

    # Success: stamp these matches so we never alert them again, and (for
    # digest users) remember when we sent so the daily limit holds.
    for m, _j in pairs:
        m.notified_at = now
    if digest:
        prefs.last_digest_at = now
    session.commit()

    report.sent = True
    report.channels = delivered
    return report


def run_alerts(
    session: SessionType,
    *,
    force_digest: bool = False,
    now: Optional[datetime] = None,
) -> list[UserAlertReport]:
    """Alert every user. One user's failure never blocks the others."""
    reports: list[UserAlertReport] = []
    for user in session.query(User).all():
        try:
            reports.append(
                send_user_alerts(session, user, force_digest=force_digest, now=now)
            )
        except Exception as exc:  # noqa: BLE001 — isolate per user
            logger.warning("alerting %s failed: %s", user.email, exc)
            session.rollback()
            reports.append(
                UserAlertReport(email=user.email, skipped_reason=f"error: {exc}")
            )
    return reports
