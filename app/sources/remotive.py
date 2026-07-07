"""
Remotive adapter — https://remotive.com/api/remote-jobs

Key-free. All jobs are remote. Supports a `search` keyword param. We filter by
recency on our side using each job's publication_date.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.sources.base import FetchedJob, JobSource, SearchQuery
from app.sources.http_util import get_json, strip_html

logger = logging.getLogger("jobbot.sources")

API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveSource(JobSource):
    name = "remotive"
    keyword_search = True

    def fetch(self, query: SearchQuery) -> list[FetchedJob]:
        params: dict = {"limit": query.max_results}
        if query.keywords:
            params["search"] = " ".join(query.keywords)
        data = get_json(API_URL, params=params)

        jobs: list[FetchedJob] = []
        for item in data.get("jobs", []):
            posted = _parse_date(item.get("publication_date"))
            if _too_old(posted, query.posted_within_days):
                continue
            jobs.append(
                FetchedJob(
                    source=self.name,
                    external_id=str(item.get("id", "")),
                    title=(item.get("title") or "").strip(),
                    company=item.get("company_name"),
                    country=None,  # remote; location is a free-text region
                    location=item.get("candidate_required_location") or "Remote",
                    work_type="Remote",
                    salary=None,  # Remotive salary is free text, not reliable
                    posted_date=posted,
                    url=item.get("url"),
                    description=strip_html(item.get("description")),
                )
            )
        return jobs


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _too_old(posted, within_days) -> bool:
    if posted is None or not within_days:
        return False
    age = (datetime.now(timezone.utc).date() - posted).days
    return age > within_days
