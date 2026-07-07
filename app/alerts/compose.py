"""
Turn a user's new matches into the subject + message bodies for each channel.

We build three renderings of the same content:
  - plain text  (email fallback + the body most mail clients show)
  - HTML        (the pretty email)
  - Slack text  (Slack's lightweight markdown)

Privacy rule (spec section 12): we NEVER include resume text — only the public
job details (title, company, where/when) and the match score.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from app.config import settings
from app.models import Job, Match, User

# Cap how many we list so a big batch doesn't make a giant email; the rest are
# summarized as "...and N more" with a link to the dashboard.
MAX_LISTED = 20


@dataclass
class Composed:
    subject: str
    text: str
    html: str
    slack: str


def _meta(job: Job) -> str:
    bits = []
    if job.work_type:
        bits.append(job.work_type)
    if job.location:
        bits.append(job.location)
    if job.posted_date:
        bits.append(f"posted {job.posted_date}")
    return f" ({', '.join(bits)})" if bits else ""


def compose(user: User, pairs: list[tuple[Match, Job]], digest: bool) -> Composed:
    n = len(pairs)
    shown = pairs[:MAX_LISTED]
    extra = n - len(shown)
    word = "match" if n == 1 else "matches"
    subject = f"JobBot {'daily digest' if digest else 'new'}: {n} job {word}"

    base = settings.app_base_url.rstrip("/")
    dash, prefs_url = f"{base}/dashboard", f"{base}/preferences"

    # --- plain text --------------------------------------------------------
    text_lines = [f"You have {n} new job {word} on JobBot:", ""]
    for m, j in shown:
        text_lines.append(f"- {m.score:.0f}% — {j.title} @ {j.company or 'Unknown company'}{_meta(j)}")
        if j.url:
            text_lines.append(f"    {j.url}")
    if extra > 0:
        text_lines.append(f"...and {extra} more.")
    text_lines += ["", f"See them all: {dash}", f"Alert settings: {prefs_url}"]
    text = "\n".join(text_lines)

    # --- HTML (escape everything from job sources) -------------------------
    items = []
    for m, j in shown:
        title = escape(j.title or "Untitled")
        if j.url:
            title = f'<a href="{escape(j.url, quote=True)}">{title}</a>'
        company = escape(j.company or "Unknown company")
        items.append(
            f"<li><b>{m.score:.0f}%</b> — {title} @ {company}"
            f"<span style='color:#888'>{escape(_meta(j))}</span></li>"
        )
    more = f"<p>…and {extra} more.</p>" if extra > 0 else ""
    html = (
        f"<p>You have <b>{n}</b> new job {word} on JobBot:</p>"
        f"<ul>{''.join(items)}</ul>{more}"
        f'<p><a href="{escape(dash, quote=True)}">See them all on your dashboard →</a></p>'
        f'<p style="color:#888;font-size:12px">You\'re getting this because you turned '
        f'on alerts in JobBot. <a href="{escape(prefs_url, quote=True)}">Change your '
        f"settings</a>.</p>"
    )

    # --- Slack (its own link syntax: <url|text>) ---------------------------
    slack_lines = [f"*JobBot — {n} new job {word}*"]
    for m, j in shown:
        label = f"{j.title} @ {j.company or 'Unknown company'}"
        link = f"<{j.url}|{label}>" if j.url else label
        slack_lines.append(f"• {m.score:.0f}% — {link}")
    if extra > 0:
        slack_lines.append(f"…and {extra} more.")
    slack_lines.append(f"<{dash}|See them all on your dashboard>")
    slack = "\n".join(slack_lines)

    return Composed(subject=subject, text=text, html=html, slack=slack)
