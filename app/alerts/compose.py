"""
Turn a user's new matches into the subject + message bodies for each channel.

We build three renderings of the same content:
  - plain text  (email fallback + the body most mail clients show)
  - HTML        (the pretty, dark "jobs you shouldn't miss" email — modelled on
                 the Indeed job-alert emails: a short why-it-fits line, a big
                 "View this job" button and a detailed job card per role)
  - Slack text  (Slack's lightweight markdown)

Email HTML is deliberately table-based with INLINE styles only: Gmail/Outlook
strip <style> blocks and ignore flt/grid, so this is what survives everywhere.

Privacy rule (spec section 12): we NEVER include resume text — only the public
job details (title, company, where/when, salary, description) and the match
score / the stored one-line "why it fits".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape

from app.config import settings
from app.models import Job, Match, User

# The email leads with the strongest few as full cards ("a couple you shouldn't
# miss"); any beyond that are summarized with a link to the dashboard.
MAX_CARDS = 3
# The plain-text fallback can afford to list more.
MAX_LISTED = 20

# ---- neutral-gray palette, modelled on the Indeed dark alert ----------------
# NOTE: every background also gets a bgcolor="" HTML attribute below — email
# clients (Gmail especially) strip CSS `background`, so without it the message
# falls back to WHITE. All bg colors are solid hex (bgcolor can't take rgba).
# ONE flat gray for the whole email (body + wrapper + content, all the same,
# every element gets bgcolor="" too) so nothing renders white around the edges.
BG = "#26282d"          # the whole email background — neutral mid-dark gray
CARD = "#26282d"        # same as BG on purpose (flat, no floating card)
JOB = "#31333b"         # each job card, a step lighter + bordered (Indeed look)
BORDER = "#41434b"      # hairline gray
INK = "#f1f3f4"         # primary text (near-white)
MUTED = "#c3c7cd"       # secondary text
FAINT = "#9aa0a6"       # captions / section labels
ACCENT = "#8f9cf7"      # Indeed's periwinkle button
ACCENT_TX = "#1a1c22"   # dark text ON the periwinkle button
LINK = "#aab6ff"        # light-indigo links
CHIP_BG = "#3d4048"     # fact pill background
CHIP_INK = "#e8eaee"
LABEL = "#9aa0a6"       # "SALARY" / "WORK SETTING" section labels
# letter-tile colors, picked by job id so a company is always the same hue
TILE = ["#5b67e8", "#159b8a", "#c07b1e", "#c85182", "#3f7be0", "#8b6df0"]

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


@dataclass
class Composed:
    subject: str
    text: str
    html: str
    slack: str


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _first_name(user: User) -> str:
    # Only greet by name when we actually have one — an email local part like
    # "mail" or "info" makes a bad first name, so fall back to a neutral "there".
    name = (user.display_name or "").strip()
    return name.split()[0] if name else "there"


def _salary_label(job: Job) -> str | None:
    lo, hi = job.salary_min, job.salary_max
    if lo and hi:
        return f"${lo // 1000}–{hi // 1000}k" if hi >= 1000 else f"${lo}–${hi}"
    one = job.salary or lo or hi
    if one:
        return f"${one // 1000}k" if one >= 10000 else f"${one:,}"
    return None


def _chips(job: Job) -> list[str]:
    """The little fact pills — only for data we actually have (no fabrication)."""
    chips: list[str] = []
    sal = _salary_label(job)
    if sal:
        chips.append(sal)
    if job.work_type:
        chips.append(job.work_type)
    if job.location:
        chips.append(job.location)
    if job.posted_date:
        chips.append(f"posted {job.posted_date}")
    return chips


def _snippet(job: Job, limit: int = 240) -> str:
    body = (job.description or "").strip().replace("\r", " ").replace("\n", " ")
    while "  " in body:
        body = body.replace("  ", " ")
    if not body:
        return ""
    return body if len(body) <= limit else body[:limit].rstrip() + "…"


def _why(m: Match, j: Job) -> str:
    """One-line 'why it fits' — the stored AI reason, or an honest fallback."""
    if m.reason and m.reason.strip():
        return m.reason.strip()
    role = j.title or "this role"
    return (
        f"One of your strongest matches right now — it scored {m.score:.0f}% "
        f"against your resume for {role}."
    )


def _meta(job: Job) -> str:
    bits = []
    if job.work_type:
        bits.append(job.work_type)
    if job.location:
        bits.append(job.location)
    if job.posted_date:
        bits.append(f"posted {job.posted_date}")
    return f" ({', '.join(bits)})" if bits else ""


# ---------------------------------------------------------------------------
# HTML building blocks (table-based, inline-styled for email clients)
# ---------------------------------------------------------------------------
def _button(url: str, label: str, *, primary: bool = True) -> str:
    """A bulletproof button — bgcolor attr + inline bg so it survives clients
    that strip CSS. Primary = Indeed's filled periwinkle with dark text;
    secondary = an outlined pill."""
    if primary:
        return (
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            f'style="margin:2px 0"><tr><td align="center" bgcolor="{ACCENT}" '
            f'style="border-radius:10px;background:{ACCENT}">'
            f'<a href="{escape(url, quote=True)}" target="_blank" '
            f'style="display:inline-block;padding:12px 26px;font-family:{FONT};font-size:14px;'
            f'font-weight:700;color:{ACCENT_TX};text-decoration:none;border-radius:10px">'
            f"{escape(label)}</a></td></tr></table>"
        )
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:2px 0"><tr><td align="center" '
        f'style="border:1px solid {ACCENT};border-radius:10px">'
        f'<a href="{escape(url, quote=True)}" target="_blank" '
        f'style="display:inline-block;padding:11px 24px;font-family:{FONT};font-size:14px;'
        f'font-weight:700;color:{LINK};text-decoration:none">{escape(label)}</a></td></tr></table>'
    )


def _fact(label: str, value: str) -> str:
    """One Indeed-style labelled fact: a caption over a value pill."""
    return (
        f'<div style="font-family:{FONT};font-size:16px;font-weight:800;color:{INK};margin:0 0 10px">{escape(label)}</div>'
        f'<span style="display:inline-block;background:{CHIP_BG};color:{CHIP_INK};'
        f'font-family:{FONT};font-size:15px;line-height:1;padding:12px 18px;border-radius:9px;'
        f'border:1px solid {BORDER}">{escape(value)}</span>'
    )


def _job_card(base: str, m: Match, j: Job) -> str:
    title = escape(j.title or "Untitled role")
    company = escape(j.company or "Company")
    initial = (j.company or j.title or "?").strip()[:1].upper()
    tile = TILE[(j.id or 0) % len(TILE)]
    view_url = f"{base}/jobs/{j.id}"

    # location under the company name
    loc = escape(j.location) if j.location else ""
    loc_html = f'<div style="color:{FAINT};font-size:14px;margin-top:3px">{loc}</div>' if loc else ""

    # Indeed-style labelled fact blocks, only for data we actually have
    facts = []
    sal = _salary_label(j)
    if sal:
        facts.append(_fact("Salary", sal))
    if j.work_type:
        facts.append(_fact("Work setting", j.work_type))
    if j.posted_date:
        facts.append(_fact("Posted", str(j.posted_date)))
    facts_html = "".join(
        f'<div style="margin:24px 0 0">{f}</div>' for f in facts
    )

    snippet = _snippet(j)
    desc_html = ""
    if snippet:
        desc_html = (
            f'<div style="height:1px;background:{BORDER};margin:26px 0 0"></div>'
            f'<div style="font-family:{FONT};font-size:16px;font-weight:800;color:{INK};margin:22px 0 10px">Job description</div>'
            f'<div style="font-family:{FONT};font-size:15px;line-height:1.7;color:{MUTED}">'
            f"{escape(snippet)} "
            f'<a href="{escape(view_url, quote=True)}" target="_blank" '
            f'style="color:{LINK};text-decoration:none;white-space:nowrap">Learn more →</a></div>'
        )

    # secondary "View original posting" button when we have the source URL
    secondary = ""
    if j.url:
        secondary = f'<div style="margin-top:8px">{_button(j.url, "View original posting →", primary=False)}</div>'

    return f"""
<div style="font-family:{FONT};font-size:15px;line-height:1.65;color:{INK};margin:0 0 14px">
  {escape(_why(m, j))}
</div>
{_button(view_url, "View this job")}
{secondary}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{JOB}"
       style="margin:16px 0 22px;background:{JOB};border:1px solid {BORDER};border-radius:14px">
  <tr><td style="padding:34px 40px 36px">
    <div style="font-family:{FONT};font-size:23px;font-weight:800;color:{INK};line-height:1.3;text-decoration:underline">{title}</div>
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:18px 0 2px">
      <tr>
        <td width="52" valign="top">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
            <td width="44" height="44" align="center" valign="middle" bgcolor="{tile}"
                style="width:44px;height:44px;background:{tile};border-radius:10px;color:#ffffff;
                       font-family:{FONT};font-weight:800;font-size:19px;text-align:center">{escape(initial)}</td>
          </tr></table>
        </td>
        <td valign="middle" style="padding-left:14px">
          <div style="font-family:{FONT};font-size:17px;font-weight:600;color:{INK}">{company}</div>
          {loc_html}
        </td>
      </tr>
    </table>
    <div style="height:1px;background:{BORDER};margin:24px 0 0"></div>
    {facts_html}
    {desc_html}
  </td></tr>
</table>"""


def _digest_html(user: User, shown, extra: int, base: str) -> str:
    dash = f"{base}/matches"
    opts = f"{base}/options"
    n_total = len(shown) + extra
    cards = "".join(_job_card(base, m, j) for m, j in shown)
    now = datetime.now()
    today = now.strftime("%A, %b ") + str(now.day)   # e.g. "Thursday, Jul 9"
    preheader = f"{n_total} new job{'s' if n_total != 1 else ''} picked for you — take a look."

    more = ""
    if extra > 0:
        more = (
            f'<div style="font-family:{FONT};font-size:13px;color:{MUTED};margin:2px 0 18px">'
            f"And <b style=\"color:{INK}\">{extra}</b> more match{'es' if extra != 1 else ''} "
            f'waiting on your dashboard.</div>'
        )

    return f"""\
<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark">
</head>
<body bgcolor="{BG}" style="margin:0;padding:0;background:{BG};">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:{BG}">{escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{BG}" style="background:{BG}">
<tr><td align="center" bgcolor="{BG}" style="background:{BG};padding:22px 0">
  <table role="presentation" width="720" cellpadding="0" cellspacing="0" border="0" bgcolor="{BG}"
         style="width:720px;max-width:100%;background:{BG}">
    <!-- header -->
    <tr><td style="padding:28px 24px 8px">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
        <td width="38" height="34" align="center" valign="middle" bgcolor="{ACCENT}"
            style="width:34px;height:34px;border-radius:9px;background:{ACCENT};color:{ACCENT_TX};
                   font-family:{FONT};font-weight:800;font-size:18px;text-align:center">J</td>
        <td valign="middle" style="padding-left:11px;font-family:{FONT};font-size:18px;font-weight:800;color:{INK}">JobBot</td>
      </tr></table>
    </td></tr>
    <!-- greeting -->
    <tr><td style="padding:16px 24px 0">
      <div style="font-family:{FONT};font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:{FAINT};margin:0 0 9px">{escape(today)}</div>
      <div style="font-family:{FONT};font-size:24px;font-weight:800;color:{INK};line-height:1.3">
        Hi {escape(_first_name(user))} — {n_total} job{'s' if n_total != 1 else ''} you shouldn't miss
      </div>
      <div style="font-family:{FONT};font-size:14.5px;line-height:1.6;color:{MUTED};margin-top:10px">
        Your strongest new matches on JobBot today, picked from your resume and preferences.
        Tap a role to see the full posting, tailor your resume and apply.
      </div>
    </td></tr>
    <!-- job cards -->
    <tr><td style="padding:24px 24px 0">
      {cards}
      {more}
      <div style="text-align:center;margin:6px 0 8px">{_button(dash, "See all my matches →")}</div>
    </td></tr>
    <!-- footer -->
    <tr><td style="padding:10px 24px 30px">
      <div style="height:1px;background:{BORDER};margin:14px 0 16px"></div>
      <div style="font-family:{FONT};font-size:12px;line-height:1.6;color:{FAINT}">
        You're getting this because email alerts are on for your JobBot account.
        Scores compare your resume to each posting; JobBot never shares your resume.
        <br><a href="{escape(opts, quote=True)}" target="_blank" style="color:{LINK};text-decoration:none">Manage alerts or turn these off</a>
        &nbsp;·&nbsp; {escape(settings.app_base_url.rstrip('/'))}
      </div>
    </td></tr>
  </table>
</td></tr>
</table>
</body></html>"""


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def compose(user: User, pairs: list[tuple[Match, Job]], digest: bool) -> Composed:
    n = len(pairs)
    cards = pairs[:MAX_CARDS]
    listed = pairs[:MAX_LISTED]
    extra_cards = n - len(cards)

    base = settings.app_base_url.rstrip("/")
    dash, opts = f"{base}/matches", f"{base}/options"

    # --- subject: lead with the top role, like a real job alert. The date
    # keeps each day's email a SEPARATE message so Gmail doesn't thread them
    # and hide the "repeated" content behind a "•••" (the click-to-expand). ---
    now = datetime.now()
    today = f"{now.strftime('%b')} {now.day}"
    top_title = (pairs[0][1].title if pairs else "New matches").strip()
    if n > 1:
        subject = f"{top_title} + {n - 1} more · JobBot · {today}"
    else:
        subject = f"{top_title} · JobBot · {today}"

    # --- plain text --------------------------------------------------------
    word = "match" if n == 1 else "matches"
    text_lines = [
        f"Hi {_first_name(user)},",
        "",
        f"{n} job {word} you shouldn't miss on JobBot today:",
        "",
    ]
    for m, j in listed:
        text_lines.append(f"* {j.title} @ {j.company or 'Company'} — {m.score:.0f}% match{_meta(j)}")
        why = _why(m, j)
        if why:
            text_lines.append(f"    {why}")
        sal = _salary_label(j)
        if sal:
            text_lines.append(f"    Salary: {sal}")
        text_lines.append(f"    View: {base}/jobs/{j.id}")
        text_lines.append("")
    if n - len(listed) > 0:
        text_lines.append(f"...and {n - len(listed)} more on your dashboard.")
        text_lines.append("")
    text_lines += [f"See them all: {dash}", f"Manage alerts: {opts}"]
    text = "\n".join(text_lines)

    # --- HTML --------------------------------------------------------------
    html = _digest_html(user, cards, extra_cards, base)

    # --- Slack -------------------------------------------------------------
    slack_lines = [f"*JobBot — {n} job {word} you shouldn't miss*"]
    for m, j in listed:
        label = f"{j.title} @ {j.company or 'Company'}"
        link = f"<{base}/jobs/{j.id}|{label}>"
        slack_lines.append(f"• {m.score:.0f}% — {link}")
    if n - len(listed) > 0:
        slack_lines.append(f"…and {n - len(listed)} more.")
    slack_lines.append(f"<{dash}|See them all on your dashboard>")
    slack = "\n".join(slack_lines)

    return Composed(subject=subject, text=text, html=html, slack=slack)
