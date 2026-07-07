"""
The always-on loop that ties Phases 2–5 together.

One CYCLE = three steps, in order:
  1. POLL    — fetch recent jobs from every source        (app/ingest.py)
  2. MATCH   — re-run the gate + score for every user      (app/matching)
  3. ALERT   — email/Slack each user their NEW matches      (app/alerts)

`run_cycle()` does that once (used by `manage.py run-once` and each scheduler
tick). `start_scheduler()` runs a cycle now and then every N minutes using
APScheduler — that's what "always-on" means: a process that wakes itself up.

Resilience: a failure in one source, one user's match, or one user's alert is
caught and logged so it never stops the rest of the cycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from app.alerts import run_alerts
from app.db import Session
from app.ingest import run_ingestion
from app.matching import compute_and_store_matches
from app.models import Preference, Resume, User
from app.sources import ENABLED_SOURCES
from app.sources.base import SearchQuery

logger = logging.getLogger("jobbot.runner")

# Resume-driven polling rotates through the term list a few searches per cycle
# (keyword APIs have daily quotas); this counter picks each cycle's slice.
_TERMS_PER_CYCLE = 3
_poll_rotation = 0


def _poll_terms(session) -> list[tuple[str, str | None, str | None]]:
    """(term, city, country) searches the sources should actively run, across
    ALL users: every parsed resume's target roles plus every typed preference
    keyword, each carrying that user's city/country so location-aware sources
    (Adzuna's `where`) return LOCAL postings, not nationwide ones."""
    searches: list[tuple[str, str | None, str | None]] = []
    seen: set[tuple[str, str]] = set()

    def _add(term: str, city: str | None, country: str | None) -> None:
        term = (term or "").strip()
        key = (term.lower(), (city or "").lower())
        if term and key not in seen:
            seen.add(key)
            searches.append((term, city or None, country or None))

    prefs_by_user = {p.user_id: p for p in session.query(Preference).all()}
    for resume in session.query(Resume).filter_by(kind="resume"):
        pref = prefs_by_user.get(resume.user_id)
        city = pref.city if pref else None
        country = pref.country if pref else None
        for role in (resume.parsed_json or {}).get("target_roles") or []:
            _add(str(role), city, country)
    for pref in prefs_by_user.values():
        for kw in pref.keywords or []:
            _add(str(kw), pref.city, pref.country)
    return searches


# Metered sources (quota-limited APIs) poll far less often than the free ones
# so their monthly budget spreads across the month. Every 8th 30-min cycle ≈
# every 4 hours ≈ 6 runs/day, 1 term each — under JSearch's ~200/mo free tier.
_METERED = {"jsearch"}
_METERED_EVERY = 8


def _run_role_search(rep, base_query, sources, term, city, country) -> None:
    q = replace(
        base_query,
        keywords=[term],
        location=city or base_query.location,
        country=country or base_query.country,
    )
    try:
        sub = run_ingestion(q, sources=sources)
    except Exception:  # noqa: BLE001 — a bad search must not kill the cycle
        logger.exception("role search %r failed", term)
        return
    rep.fetched += sub.total_fetched
    rep.new_jobs += sub.new_jobs
    where = f" near {city}" if city else ""
    names = "/".join(s.name for s in sources)
    logger.info("role search '%s'%s [%s]: %d fetched, %d new", term, where, names, sub.total_fetched, sub.new_jobs)
    rep.source_lines.append(f"role search '{term}'{where}: {sub.total_fetched} fetched, {sub.new_jobs} new")


def _poll_role_searches(rep: "CycleReport", base_query: SearchQuery) -> None:
    """Extra POLL step: search the keyword-capable sources for resume-driven
    terms. FREE sources (adzuna/remotive/usajobs) run every cycle for a slice
    of terms; METERED sources (jsearch) run one term only every _METERED_EVERY
    cycles (plus their own hard monthly cap) to protect the free-tier quota."""
    global _poll_rotation

    kw_sources = [s for s in ENABLED_SOURCES if s.keyword_search and s.is_configured()]
    if not kw_sources:
        return
    free = [s for s in kw_sources if s.name not in _METERED]
    metered = [s for s in kw_sources if s.name in _METERED]

    with Session() as session:
        terms = _poll_terms(session)
    if not terms:
        return

    cycle = _poll_rotation
    _poll_rotation += 1

    # Free sources: a rotating batch of terms every cycle.
    if free:
        take = min(_TERMS_PER_CYCLE, len(terms))
        start = (cycle * take) % len(terms)
        for i in range(take):
            term, city, country = terms[(start + i) % len(terms)]
            _run_role_search(rep, base_query, free, term, city, country)

    # Metered sources: one term, only occasionally.
    if metered and cycle % _METERED_EVERY == 0:
        term, city, country = terms[(cycle // _METERED_EVERY) % len(terms)]
        _run_role_search(rep, base_query, metered, term, city, country)


@dataclass
class CycleReport:
    started_at: datetime
    fetched: int = 0
    new_jobs: int = 0
    users_matched: int = 0
    matches_stored: int = 0
    alerts_sent: int = 0
    source_lines: list[str] = field(default_factory=list)
    alert_lines: list[str] = field(default_factory=list)

    def one_line(self) -> str:
        return (
            f"{self.new_jobs} new job(s), "
            f"{self.matches_stored} match(es) across {self.users_matched} user(s), "
            f"{self.alerts_sent} alert(s) sent"
        )

    def summary(self) -> str:
        lines = ["Cycle summary:", "  POLL:"]
        lines += [f"    - {s}" for s in self.source_lines]
        lines.append(f"    => {self.new_jobs} new job(s) stored ({self.fetched} fetched).")
        lines.append(
            f"  MATCH: {self.matches_stored} match(es) stored/updated "
            f"across {self.users_matched} user(s) with a resume."
        )
        lines.append(f"  ALERT: {self.alerts_sent} user(s) notified.")
        lines += [f"    - {a}" for a in self.alert_lines]
        return "\n".join(lines)


def run_cycle(
    query: SearchQuery,
    *,
    send: bool = True,
    force_digest: bool = False,
) -> CycleReport:
    """Run one poll -> match -> alert cycle and return a report."""
    rep = CycleReport(started_at=datetime.now(timezone.utc))

    # --- 1. POLL -----------------------------------------------------------
    ingest_report = run_ingestion(query)
    rep.fetched = ingest_report.total_fetched
    rep.new_jobs = ingest_report.new_jobs
    for s in ingest_report.sources:
        if s.skipped:
            status = "skipped (not configured)"
        elif s.error:
            status = f"ERROR: {s.error}"
        else:
            status = f"{s.fetched} fetched"
        rep.source_lines.append(f"{s.name}: {status}")

    # --- 1b. resume-driven role searches ------------------------------------
    # When the scheduler polls with no fixed keywords, actively search the
    # keyword-capable sources for what users' resumes are qualified for.
    if not query.keywords:
        _poll_role_searches(rep, query)

    # --- 2. MATCH (+ auto-kits) + 3. ALERT + 4. FOLLOW-UPS ------------------
    with Session() as session:
        for user in session.query(User).all():
            try:
                result = compute_and_store_matches(session, user)
                if not result.get("skipped_reason"):
                    rep.users_matched += 1
                    rep.matches_stored += result.get("stored", 0)
            except Exception as exc:  # noqa: BLE001 — one user can't break the cycle
                logger.warning("matching %s failed: %s", user.email, exc)
                session.rollback()
                continue
            # Auto-build Application Kits for this user's strongest new
            # matches (capped per day + by the monthly AI budget), BEFORE
            # alerting — so the briefing can say "✨ kit ready".
            try:
                from app.kit_auto import auto_build_kits

                built = auto_build_kits(session, user)
                if built:
                    rep.source_lines.append(f"auto-kits: {built} built for {user.email}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("auto-kits for %s failed: %s", user.email, exc)
                session.rollback()

        if send:
            for r in run_alerts(session, force_digest=force_digest):
                if r.sent:
                    rep.alerts_sent += 1
                    rep.alert_lines.append(
                        f"{r.email}: sent {r.match_count} via {', '.join(r.channels)}"
                    )
                elif r.match_count:
                    # had matches but held back (e.g. digest timing) — worth noting
                    rep.alert_lines.append(
                        f"{r.email}: held ({r.skipped_reason}, {r.match_count} pending)"
                    )
            # Post-application follow-up nudges (one per applied job, after
            # JOBBOT_FOLLOWUP_DAYS of silence).
            try:
                from app.followups import run_followups

                nudged = run_followups(session)
                if nudged:
                    rep.alert_lines.append(f"follow-up nudges sent: {nudged}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("follow-ups failed: %s", exc)
                session.rollback()

    return rep


def start_scheduler(
    query: SearchQuery,
    interval_minutes: int,
    *,
    force_digest: bool = False,
) -> None:
    """Run a cycle now, then every `interval_minutes`, until Ctrl+C."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone="UTC")

    def tick() -> None:
        try:
            rep = run_cycle(query, force_digest=force_digest)
            logger.info("cycle done — %s", rep.one_line())
        except Exception:  # noqa: BLE001 — keep the scheduler alive no matter what
            logger.exception("cycle failed; will try again next interval")

    # next_run_time = now makes the first cycle fire immediately, then repeat.
    scheduler.add_job(
        tick,
        "interval",
        minutes=interval_minutes,
        next_run_time=datetime.now(timezone.utc),
        id="poll_match_alert",
        max_instances=1,  # don't overlap if a cycle runs long
        coalesce=True,
    )
    logger.info(
        "Scheduler started: a poll->match->alert cycle now, then every %d minute(s). "
        "Press Ctrl+C to stop.",
        interval_minutes,
    )
    scheduler.start()  # blocks
