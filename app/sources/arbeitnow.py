"""
Arbeitnow adapter — https://www.arbeitnow.com/api/job-board-api

Key-free, Europe-heavy board. No server-side search, so we filter by keyword and
recency ourselves. Each job carries a `remote` boolean and `created_at` (a Unix
timestamp).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.sources.base import (
    FetchedJob,
    JobSource,
    SearchQuery,
    infer_work_type,
    matches_any_keyword,
)
from app.sources.http_util import get_json, strip_html

logger = logging.getLogger("jobbot.sources")

API_URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowSource(JobSource):
    name = "arbeitnow"

    def fetch(self, query: SearchQuery) -> list[FetchedJob]:
        data = get_json(API_URL)
        jobs: list[FetchedJob] = []
        for item in data.get("data", []):
            title = (item.get("title") or "").strip()
            description = strip_html(item.get("description"))
            tags = " ".join(item.get("tags") or [])
            if not matches_any_keyword(query, title, description, tags):
                continue
            posted = _parse_date(item.get("created_at"))
            if _too_old(posted, query.posted_within_days):
                continue
            work_type = infer_work_type(
                title, item.get("location"), description,
                remote_flag=bool(item.get("remote")),
            )
            jobs.append(
                FetchedJob(
                    source=self.name,
                    external_id=str(item.get("slug", "")),
                    title=title,
                    company=item.get("company_name"),
                    country=None,
                    location=item.get("location"),
                    work_type=work_type,
                    salary=None,
                    posted_date=posted,
                    url=item.get("url"),
                    description=description,
                )
            )
            if len(jobs) >= query.max_results:
                break
        return jobs


def _parse_date(value):
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).date()
    except (TypeError, ValueError, OSError):
        return None


def _too_old(posted, within_days) -> bool:
    if posted is None or not within_days:
        return False
    age = (datetime.now(timezone.utc).date() - posted).days
    return age > within_days
