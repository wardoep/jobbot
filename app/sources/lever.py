"""Lever public postings adapter (BUILD_SPEC).

  https://api.lever.co/v0/postings/{slug}?mode=json   -> a JSON list of postings.

Each posting's full body is assembled from `description` + the `lists` sections +
`additional`. Dates are epoch milliseconds; remote type comes from `workplaceType`.
"""

from __future__ import annotations

import logging

from app.sources.ats_util import (
    build_job, normalize_remote, parse_epoch_ms, parse_salary_text, salary_from_components, to_plain,
)
from app.sources.base import FetchedJob
from app.sources.http_util import get_json

logger = logging.getLogger("jobbot.sources.lever")

PROVIDER = "lever"
_URL = "https://api.lever.co/v0/postings/{slug}"


def _full_html(p: dict) -> str:
    parts = [p.get("description") or ""]
    for sec in (p.get("lists") or []):
        parts.append(f"<h3>{sec.get('text', '')}</h3>{sec.get('content', '')}")
    parts.append(p.get("additional") or "")
    return "\n".join(x for x in parts if x)


def fetch(slug: str, company_name: str) -> list[FetchedJob]:
    """Return all postings for one Lever company. Never raises."""
    try:
        data = get_json(_URL.format(slug=slug), params={"mode": "json"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("lever %s fetch failed: %s", slug, exc)
        return []

    postings = data if isinstance(data, list) else (data.get("data") or [])
    out: list[FetchedJob] = []
    for p in postings:
        try:
            cats = p.get("categories") or {}
            location = cats.get("location")
            html = _full_html(p)
            plain = p.get("descriptionPlain") or to_plain(html)
            remote_type = normalize_remote(p.get("workplaceType"), None, location, p.get("text"), plain)
            salary = salary_from_components(p.get("salaryRange"))
            if salary == (None, None, None):
                salary = parse_salary_text(plain)
            out.append(build_job(
                source=PROVIDER,
                external_id=p.get("id"),
                title=p.get("text"),
                company=company_name,
                location=location,
                country=p.get("country"),
                html=html,
                plain=plain,
                url=p.get("hostedUrl") or p.get("applyUrl"),
                posted_at=parse_epoch_ms(p.get("createdAt")),
                remote_type=remote_type,
                salary=salary,
                ats_provider=PROVIDER,
                ats_id=slug,
            ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("lever %s: skipped a posting: %s", slug, exc)
    return out
