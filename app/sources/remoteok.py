"""
RemoteOK adapter — https://remoteok.com/api

Key-free. All jobs are remote. The API returns a JSON list whose FIRST element
is a legal/metadata notice (not a job) — we skip it. No server-side search, so
we filter by keyword and recency on our side.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.sources.base import FetchedJob, JobSource, SearchQuery, matches_any_keyword
from app.sources.http_util import get_json, strip_html

logger = logging.getLogger("jobbot.sources")

API_URL = "https://remoteok.com/api"


class RemoteOKSource(JobSource):
    name = "remoteok"

    def fetch(self, query: SearchQuery) -> list[FetchedJob]:
        data = get_json(API_URL)
        if not isinstance(data, list):
            return []

        jobs: list[FetchedJob] = []
        for item in data:
            # Skip the legal notice / any non-job rows.
            if not isinstance(item, dict) or not item.get("position"):
                continue
            title = (item.get("position") or "").strip()
            description = strip_html(item.get("description"))
            tags = " ".join(item.get("tags") or [])
            if not matches_any_keyword(query, title, description, tags):
                continue
            posted = _parse_date(item.get("date"))
            if _too_old(posted, query.posted_within_days):
                continue
            jobs.append(
                FetchedJob(
                    source=self.name,
                    external_id=str(item.get("id") or item.get("slug") or ""),
                    title=title,
                    company=item.get("company"),
                    country=None,
                    location=item.get("location") or "Remote",
                    work_type="Remote",
                    salary=_to_int(item.get("salary_min")),
                    posted_date=posted,
                    url=item.get("url") or item.get("apply_url"),
                    description=description,
                )
            )
            if len(jobs) >= query.max_results:
                break
        return jobs


def _to_int(value):
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _too_old(posted, within_days) -> bool:
    if posted is None or not within_days:
        return False
    age = (datetime.now(timezone.utc).date() - posted).days
    return age > within_days
