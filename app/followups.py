"""
Post-application follow-up nudges.

When a job has sat in "applied" for JOBBOT_FOLLOWUP_DAYS (default 7) with no
change, JobBot nudges the user once — via Telegram when connected, else email
— with a short, ready-to-send follow-up note drafted for that job. The nudge
is drafted, never sent to the employer: following up stays in the user's hands.

Each Star gets at most ONE nudge (stamped in Star.followup_at). Drafting costs
one AI call (budget-capped); if the budget is out, a clean static template is
used instead so the nudge still goes out.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as SessionType

from app.alerts.email import send_email
from app.alerts.telegram import send_telegram
from app.config import settings
from app.llm_budget import try_spend
from app.models import Job, Star, User

logger = logging.getLogger("jobbot.followups")


def _draft_followup(session: SessionType, user: User, job: Job, days: int) -> str:
    """A short follow-up email body — AI-drafted, static template as fallback."""
    name = (user.display_name or user.email.split("@")[0]).strip()
    fallback = (
        f"Subject: Following up on my {job.title} application\n\n"
        f"Hi {job.company or 'there'} team,\n\n"
        f"I applied for the {job.title} position about {days} days ago and "
        "wanted to follow up — I remain very interested in the role and would "
        "welcome the chance to talk about how I can contribute. Happy to "
        "provide anything else you need.\n\n"
        f"Best regards,\n{name}"
    )
    try:
        from app.llm import get_default_provider

        if not try_spend(session, 1):
            return fallback
        provider = get_default_provider()
        system = (
            "Write a SHORT, professional follow-up email (subject line + body, "
            "5 sentences max) from a candidate who applied about "
            f"{days} days ago and heard nothing. Polite, specific, confident — "
            "reaffirm interest, offer to provide more, no guilt-tripping, no "
            "invented facts. Plain text starting with 'Subject: '."
        )
        user_msg = (
            f"Job: {job.title} at {job.company or 'the company'}\n"
            f"Candidate name: {name}\n"
            "Write the follow-up email now."
        )
        text = provider.complete(system, user_msg, max_output_tokens=280, temperature=0.4)
        return text.strip() or fallback
    except Exception as exc:  # noqa: BLE001 — nudges must never crash a cycle
        logger.warning("follow-up draft failed (%s); using template", exc)
        return fallback


def run_followups(session: SessionType) -> int:
    """Send due follow-up nudges across all users. Returns # sent."""
    days = settings.followup_days
    if days <= 0:
        return 0
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    due = (
        session.query(Star, Job, User)
        .join(Job, Star.job_id == Job.id)
        .join(User, Star.user_id == User.id)
        .filter(Star.status == "applied", Star.followup_at.is_(None))
        .all()
    )
    sent = 0
    for star, job, user in due:
        applied_at = star.created_at
        if applied_at is not None and applied_at.tzinfo is None:
            applied_at = applied_at.replace(tzinfo=timezone.utc)
        if applied_at is None or applied_at > cutoff:
            continue

        age = (now - applied_at).days
        draft = _draft_followup(session, user, job, age)
        base = settings.app_base_url.rstrip("/")
        text = (
            f"⏰ <b>Time to follow up</b>\n\n"
            f"You applied to <a href=\"{base}/jobs/{job.id}\">{job.title}</a>"
            f"{' at ' + job.company if job.company else ''} {age} days ago with "
            f"no reply yet. A short nudge often gets a response — here's a "
            f"draft you can copy:\n\n<pre>{draft}</pre>"
        )
        delivered = False
        if user.telegram_chat_id:
            delivered = send_telegram(user.telegram_chat_id, text)
        if not delivered:
            plain = (
                f"You applied to {job.title}"
                f"{' at ' + job.company if job.company else ''} {age} days ago "
                f"with no reply yet. Here's a follow-up draft:\n\n{draft}\n\n"
                f"Open the job: {base}/jobs/{job.id}"
            )
            res = send_email(user.email, "Time to follow up on your application", plain, None)
            delivered = bool(res.ok)
        if delivered:
            star.followup_at = now
            session.commit()
            sent += 1
            logger.info("follow-up nudge sent to %s for job %s", user.email, job.id)
    return sent
