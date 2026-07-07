"""ATS ingestion runner (BUILD_SPEC, ingestion-only phase).

For each seeded company: upsert a `companies` row, fetch its public ATS board via
the matching adapter, dedupe (within the run + against existing jobs), compute a
simple `ghost_score`, and insert `Job` rows — filling BOTH the spec columns and the
legacy columns the existing UI/matching read. Mirrors the structure of app/ingest.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session as SessionType

from app.db import Session
from app.models import Company, Job
from app.sources import ashby, greenhouse, lever
from app.sources.base import FetchedJob
from app.sources.companies_seed import ATS_COMPANIES

logger = logging.getLogger("jobbot.ats_ingest")

_ADAPTERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}


@dataclass
class CompanyReport:
    name: str
    provider: str
    fetched: int = 0
    inserted: int = 0
    skipped: int = 0
    error: Optional[str] = None


@dataclass
class AtsReport:
    companies: list[CompanyReport] = field(default_factory=list)

    @property
    def fetched(self) -> int:
        return sum(c.fetched for c in self.companies)

    @property
    def inserted(self) -> int:
        return sum(c.inserted for c in self.companies)

    @property
    def skipped(self) -> int:
        return sum(c.skipped for c in self.companies)

    @property
    def companies_hit(self) -> int:
        return sum(1 for c in self.companies if c.fetched > 0)

    def summary(self) -> str:
        lines = [
            f"ATS ingestion: {self.companies_hit}/{len(self.companies)} companies returned jobs; "
            f"fetched {self.fetched}, inserted {self.inserted} new, skipped {self.skipped} "
            f"(dupes/known).",
            "",
        ]
        for c in self.companies:
            status = c.error or f"fetched {c.fetched}, +{c.inserted} new, {c.skipped} skipped"
            lines.append(f"  {c.provider:11s} {c.name:14s} {status}")
        return "\n".join(lines)


def _sort_ts(fj: FetchedJob) -> float:
    """Epoch seconds for sorting newest-first; 0 when the date is unknown."""
    pa = fj.posted_at
    if pa is None:
        return 0.0
    if pa.tzinfo is None:
        pa = pa.replace(tzinfo=timezone.utc)
    return pa.timestamp()


def _ghost_score(fj: FetchedJob, now: datetime) -> float:
    """Simple v1 heuristic 0..1: stale postings + very short/templated bodies."""
    score = 0.0
    if fj.posted_at:
        pa = fj.posted_at if fj.posted_at.tzinfo else fj.posted_at.replace(tzinfo=timezone.utc)
        age = (now - pa).days
        if age > 120:
            score += 0.5
        elif age > 60:
            score += 0.3
        elif age > 30:
            score += 0.15
    if len(fj.description_md or fj.description or "") < 400:
        score += 0.3
    return round(min(score, 1.0), 2)


def _upsert_company(session: SessionType, name: str, provider: str, slug: str) -> Company:
    c = session.query(Company).filter_by(ats_provider=provider, ats_id=slug).first()
    if c is None:
        c = Company(name=name, ats_provider=provider, ats_id=slug)
        session.add(c)
        session.flush()  # get c.id
    elif c.name != name:
        c.name = name
    return c


def _to_row(fj: FetchedJob, company_id: int, now: datetime) -> Job:
    return Job(
        # legacy columns (UI + matching read these) ---------------------------
        source=fj.source,
        external_id=fj.external_id or None,
        title=fj.title,
        company=fj.company,
        country=fj.country,
        location=fj.location,
        work_type=fj.work_type,
        salary=fj.salary,
        posted_date=fj.posted_date,
        url=fj.url,
        description=fj.description,
        fetched_at=now,
        dedupe_key=fj.dedupe_key,
        # BUILD_SPEC columns --------------------------------------------------
        company_id=company_id,
        remote_type=fj.remote_type,
        salary_min=fj.salary_min,
        salary_max=fj.salary_max,
        salary_currency=fj.salary_currency,
        description_md=fj.description_md or None,
        posted_at=fj.posted_at,
        ghost_score=_ghost_score(fj, now),
    )


def run_ats_ingestion(
    session: Optional[SessionType] = None,
    companies: Optional[list[tuple[str, str, str]]] = None,
    per_company_cap: int = 80,
) -> AtsReport:
    """Pull every seeded company's ATS board and store the new postings.

    `per_company_cap` keeps the first run sane (newest N per company); pass 0 for no cap.
    """
    own = session is None
    session = session or Session()
    now = datetime.now(timezone.utc)
    seed = companies if companies is not None else ATS_COMPANIES
    report = AtsReport()

    # Snapshot known keys once, then keep them current as we insert.
    existing_ext = {(s, e) for (s, e) in session.query(Job.source, Job.external_id).all()}
    existing_keys = {k for (k,) in session.query(Job.dedupe_key).all()}

    try:
        for name, provider, slug in seed:
            cr = CompanyReport(name=name, provider=provider)
            adapter = _ADAPTERS.get(provider)
            if adapter is None:
                cr.error = f"no adapter for provider '{provider}'"
                report.companies.append(cr)
                continue

            jobs = adapter.fetch(slug, name)  # adapters never raise
            cr.fetched = len(jobs)
            if not jobs:
                cr.error = "no jobs (feed empty/unreachable)"
                report.companies.append(cr)
                continue

            jobs.sort(key=_sort_ts, reverse=True)  # newest first
            if per_company_cap:
                jobs = jobs[:per_company_cap]

            company = _upsert_company(session, name, provider, slug)
            for fj in jobs:
                if not fj.title:
                    continue
                key = fj.dedupe_key
                if (fj.source, fj.external_id) in existing_ext or key in existing_keys:
                    cr.skipped += 1
                    continue
                session.add(_to_row(fj, company.id, now))
                existing_ext.add((fj.source, fj.external_id))
                existing_keys.add(key)
                cr.inserted += 1

            session.commit()  # persist per company (bounded memory, partial progress)
            report.companies.append(cr)
            logger.info(
                "ats %s/%s: fetched=%d inserted=%d skipped=%d",
                provider, slug, cr.fetched, cr.inserted, cr.skipped,
            )
    finally:
        if own:
            session.close()
    return report
