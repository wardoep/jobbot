"""
Auto-build Application Kits for a user's strongest new matches.

Runs inside each scheduler cycle, right after matching: any match scoring at
or above JOBBOT_AUTO_KIT_THRESHOLD (default 80) that has no kit yet gets one
generated in the background — so by the time the user opens the job, the
tailored resume, cover letter and portal answers are already waiting
("✨ kit ready" in their Telegram briefing).

Cost containment (kits cost 2 AI calls each):
  * at most JOBBOT_AUTO_KITS_PER_DAY per user per day (default 3; 0 = off),
    counted by ApplicationKit.created_at — no extra bookkeeping;
  * every generation still passes the global monthly AI budget
    (llm_budget.try_spend), so a burst of users can't run up the bill;
  * refused / already-applied jobs are skipped — no point prepping those.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone

from sqlalchemy.orm import Session as SessionType

from app.assist import LLMError, build_application_kit, tailor_resume_structured
from app.config import settings
from app.llm_budget import try_spend
from app.models import ApplicationKit, Job, Match, Resume, Star, User

logger = logging.getLogger("jobbot.kits")


def auto_build_kits(session: SessionType, user: User) -> int:
    """Build kits for the user's best un-kitted matches. Returns # built."""
    per_day = settings.auto_kits_per_day
    if per_day <= 0:
        return 0

    resume_rows = (
        session.query(Resume).filter_by(user_id=user.id, kind="resume").all()
    )
    resume_text = "\n".join(r.raw_text for r in resume_rows if r.raw_text).strip()
    if not resume_text:
        return 0

    # Today's quota: kits already created since UTC midnight count against it.
    midnight = datetime.combine(
        datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc
    )
    built_today = (
        session.query(ApplicationKit)
        .filter(
            ApplicationKit.user_id == user.id,
            ApplicationKit.created_at >= midnight,
        )
        .count()
    )
    remaining = per_day - built_today
    if remaining <= 0:
        return 0

    kitted = {
        k.job_id for k in session.query(ApplicationKit.job_id).filter_by(user_id=user.id)
    }
    decided = {
        s.job_id: s.status for s in session.query(Star).filter_by(user_id=user.id)
    }
    candidates = (
        session.query(Match, Job)
        .join(Job, Match.job_id == Job.id)
        .filter(
            Match.user_id == user.id,
            Match.score >= settings.auto_kit_threshold,
        )
        .order_by(Match.score.desc())
        .all()
    )

    built = 0
    for match, job in candidates:
        if built >= remaining:
            break
        if job.id in kitted:
            continue
        if decided.get(job.id) in ("rejected", "applied"):
            continue  # not interested / already applied — kit adds nothing
        if not try_spend(session, 2):
            logger.info("auto-kits stopped — monthly AI budget exhausted")
            break
        try:
            content = build_application_kit(resume_text, job)
            content["resume"] = tailor_resume_structured(resume_text, job)
        except LLMError as exc:
            logger.warning("auto-kit for job %s failed: %s", job.id, exc)
            continue
        session.add(ApplicationKit(user_id=user.id, job_id=job.id, content=content))
        session.commit()
        built += 1
        logger.info(
            "auto-built kit for %s: %s @ %s (score %.0f)",
            user.email, job.title, job.company, match.score,
        )
    return built
