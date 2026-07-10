"""
Ingestion orchestrator: run every job source, normalize, deduplicate, store.

Flow:
  1. Ask each enabled adapter for jobs (each wrapped in try/except so ONE broken
     source never stops the others — the spec's core resilience rule).
  2. Deduplicate within this batch by `dedupe_key` (same job from two boards).
  3. Skip jobs already in the DB — either the exact (source, external_id) we saw
     before, OR an equivalent job (same dedupe_key) already stored from any source.
  4. Insert the genuinely new jobs and report what happened.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.db import Session
from app.models import Job
from app.sources import ENABLED_SOURCES
from app.sources.base import FetchedJob, JobSource, SearchQuery

logger = logging.getLogger("jobbot.ingest")


@dataclass
class SourceResult:
    name: str
    fetched: int = 0
    error: str | None = None
    skipped: bool = False  # not configured (e.g. missing API key)


@dataclass
class IngestReport:
    sources: list[SourceResult] = field(default_factory=list)
    new_jobs: int = 0
    duplicates: int = 0
    total_fetched: int = 0

    def summary(self) -> str:
        lines = ["Ingestion summary:"]
        for s in self.sources:
            if s.skipped:
                status = "skipped (not configured)"
            elif s.error:
                status = f"ERROR: {s.error}"
            else:
                status = f"{s.fetched} fetched"
            lines.append(f"  - {s.name:<10} {status}")
        lines.append(
            f"Stored {self.new_jobs} new job(s); "
            f"{self.duplicates} were duplicates; "
            f"{self.total_fetched} fetched across all sources."
        )
        return "\n".join(lines)


def run_ingestion(
    query: SearchQuery,
    sources: list[JobSource] | None = None,
) -> IngestReport:
    sources = sources if sources is not None else ENABLED_SOURCES
    report = IngestReport()

    # --- 1. Collect from every source independently ----------------------
    collected: list[FetchedJob] = []
    for source in sources:
        result = SourceResult(name=source.name)
        if not source.is_configured():
            result.skipped = True
            report.sources.append(result)
            continue
        try:
            jobs = source.fetch(query)
            # Drop obviously empty rows (no title = unusable for matching).
            jobs = [j for j in jobs if j.title]
            result.fetched = len(jobs)
            collected.extend(jobs)
        except Exception as exc:  # noqa: BLE001 — isolate every source
            result.error = f"{type(exc).__name__}: {exc}"
            logger.warning("source %s failed: %s", source.name, result.error)
        report.sources.append(result)

    report.total_fetched = len(collected)

    # --- 2. Deduplicate within this batch by dedupe_key ------------------
    batch: dict[str, FetchedJob] = {}
    for job in collected:
        batch.setdefault(job.dedupe_key, job)

    # --- 3 & 4. Skip already-known jobs, insert the rest -----------------
    with Session() as session:
        existing_ext = {
            (s, e)
            for (s, e) in session.query(Job.source, Job.external_id).all()
        }
        existing_keys = {k for (k,) in session.query(Job.dedupe_key).all()}

        now = datetime.now(timezone.utc)
        for key, job in batch.items():
            if (job.source, job.external_id) in existing_ext or key in existing_keys:
                report.duplicates += 1
                continue
            session.add(_to_row(job, now))
            existing_keys.add(key)  # guard against intra-batch race on same key
            report.new_jobs += 1

        session.commit()

    return report


def _to_row(job: FetchedJob, fetched_at: datetime) -> Job:
    return Job(
        source=job.source,
        external_id=job.external_id or None,
        title=job.title,
        company=job.company,
        country=job.country,
        location=job.location,
        work_type=job.work_type,
        salary=job.salary,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        posted_date=job.posted_date,
        url=job.url,
        description=job.description,
        fetched_at=fetched_at,
        dedupe_key=job.dedupe_key,
    )
