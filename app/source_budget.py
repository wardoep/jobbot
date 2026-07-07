"""
Monthly request budget for metered job sources (e.g. JSearch's free tier is
~200 requests/month). Mirrors app/llm_budget.py: a per-service, per-calendar-
month counter in the source_usage table that refuses to spend past the cap,
so a metered source self-skips instead of running up a bill.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session as SessionType

from app.models import SourceUsage


def _month_key(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def usage(session: SessionType, service: str) -> int:
    """Calls made by `service` this calendar month."""
    row = (
        session.query(SourceUsage)
        .filter_by(service=service, month=_month_key())
        .first()
    )
    return row.calls if row else 0


def try_spend(session: SessionType, service: str, cap: int, calls: int = 1) -> bool:
    """Record `calls` against this month if the cap allows (cap 0 = unlimited).

    Returns False (recording nothing) once the month's budget is exhausted.
    Counts attempts, not successes — a failed request still spent quota.
    """
    row = (
        session.query(SourceUsage)
        .filter_by(service=service, month=_month_key())
        .first()
    )
    if row is None:
        row = SourceUsage(service=service, month=_month_key(), calls=0)
        session.add(row)
    if cap and row.calls + calls > cap:
        return False
    row.calls += calls
    session.commit()
    return True
