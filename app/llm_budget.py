"""
Monthly budget for AI-scoring API calls.

Public self-signup means strangers can create accounts, upload a resume, and
have the matcher spend OpenAI calls scoring jobs for them. This module keeps
a per-calendar-month call counter in the `llm_usage` table and refuses to
spend past the cap, so the worst case is bounded no matter how many accounts
appear. When the cap is hit, matching falls back to the free TF-IDF scores
for the rest of the month (cached AI verdicts keep working — reads are free).

Configure with JOBBOT_LLM_MONTHLY_CAP in .env:
  1000 (default) ≈ a few dollars/month of gpt-4o-mini at worst
  0 or empty     = unlimited
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session as SessionType

from app.config import settings
from app.models import LlmUsage

log = logging.getLogger("jobbot.llm.budget")


def monthly_cap() -> int:
    """The configured cap; 0 means unlimited."""
    return max(0, settings.llm_monthly_cap)


def _month_key(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def month_usage(session: SessionType) -> tuple[int, int]:
    """Return (calls made this month, cap). Cap 0 = unlimited."""
    row = session.get(LlmUsage, _month_key())
    return (row.calls if row else 0), monthly_cap()


def try_spend(session: SessionType, calls: int = 1) -> bool:
    """Record `calls` API calls against this month if the cap allows.

    Returns False (and records nothing) once the month's budget is exhausted.
    Counts attempts, not successes — a failed API call still spent a request.
    """
    cap = monthly_cap()
    row = session.get(LlmUsage, _month_key())
    if row is None:
        row = LlmUsage(month=_month_key(), calls=0)
        session.add(row)
    if cap and row.calls + calls > cap:
        return False
    row.calls += calls
    session.commit()
    return True
