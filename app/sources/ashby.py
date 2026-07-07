"""Ashby public job-board adapter (BUILD_SPEC).

  https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true

Ashby gives real HTML (`descriptionHtml`) + `descriptionPlain`, an explicit
`isRemote`/`workplaceType`, and structured `compensation` when published.
"""

from __future__ import annotations

import logging

from app.sources.ats_util import (
    build_job, normalize_remote, parse_iso, parse_salary_text, salary_from_components,
)
from app.sources.base import FetchedJob
from app.sources.http_util import get_json

logger = logging.getLogger("jobbot.sources.ashby")

PROVIDER = "ashby"
_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def fetch(slug: str, company_name: str) -> list[FetchedJob]:
    """Return all listed postings for one Ashby company. Never raises."""
    try:
        data = get_json(_URL.format(slug=slug), params={"includeCompensation": "true"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("ashby %s fetch failed: %s", slug, exc)
        return []

    out: list[FetchedJob] = []
    for job in (data.get("jobs") or []):
        try:
            if job.get("isListed") is False:
                continue
            plain = job.get("descriptionPlain")
            html = job.get("descriptionHtml")
            location = job.get("location")
            remote_type = normalize_remote(
                job.get("workplaceType"), job.get("isRemote"), location, job.get("title"), plain
            )
            salary = salary_from_components(job.get("compensation"))
            if salary == (None, None, None):
                salary = parse_salary_text(plain)
            out.append(build_job(
                source=PROVIDER,
                external_id=job.get("id"),
                title=job.get("title"),
                company=company_name,
                location=location,
                html=html,
                plain=plain,
                url=job.get("jobUrl") or job.get("applyUrl"),
                posted_at=parse_iso(job.get("publishedAt")),
                remote_type=remote_type,
                salary=salary,
                ats_provider=PROVIDER,
                ats_id=slug,
            ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("ashby %s: skipped a posting: %s", slug, exc)
    return out
