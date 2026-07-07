"""Greenhouse public job-board adapter (BUILD_SPEC).

One request per company returns every posting WITH its HTML content:
  https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true

Greenhouse returns `content` HTML-entity-escaped; `ats_util.to_markdown` unescapes
it. There's no explicit remote flag, so remote type is inferred from text.
"""

from __future__ import annotations

import logging

from app.sources.ats_util import build_job, parse_iso, parse_salary_text, normalize_remote, to_plain
from app.sources.base import FetchedJob
from app.sources.http_util import get_json

logger = logging.getLogger("jobbot.sources.greenhouse")

PROVIDER = "greenhouse"
_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def fetch(slug: str, company_name: str) -> list[FetchedJob]:
    """Return all listed postings for one Greenhouse company. Never raises."""
    try:
        data = get_json(_URL.format(slug=slug), params={"content": "true"})
    except Exception as exc:  # noqa: BLE001 — skip a dead/blocked board
        logger.warning("greenhouse %s fetch failed: %s", slug, exc)
        return []

    out: list[FetchedJob] = []
    for job in (data.get("jobs") or []):
        try:
            content = job.get("content")
            plain = to_plain(content)
            location = (job.get("location") or {}).get("name")
            remote_type = normalize_remote(None, None, job.get("title"), location, plain)
            salary = parse_salary_text(plain)
            out.append(build_job(
                source=PROVIDER,
                external_id=job.get("id"),
                title=job.get("title"),
                company=company_name,
                location=location,
                html=content,
                plain=plain,
                url=job.get("absolute_url"),
                posted_at=parse_iso(job.get("first_published") or job.get("updated_at")),
                remote_type=remote_type,
                salary=salary,
                ats_provider=PROVIDER,
                ats_id=slug,
            ))
        except Exception as exc:  # noqa: BLE001 — one bad posting can't break the rest
            logger.warning("greenhouse %s: skipped a posting: %s", slug, exc)
    return out
