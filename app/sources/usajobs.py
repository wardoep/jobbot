"""
USAJOBS adapter — https://developer.usajobs.gov/

US federal government jobs. Needs a free API key + the email you registered,
sent in request headers. If those aren't set in .env, this source cleanly
skips itself (returns nothing) instead of failing the run.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.config import settings
from app.sources.base import FetchedJob, JobSource, SearchQuery, infer_work_type
from app.sources.http_util import get_json, strip_html

logger = logging.getLogger("jobbot.sources")

API_URL = "https://data.usajobs.gov/api/search"


class USAJobsSource(JobSource):
    name = "usajobs"
    keyword_search = True

    def is_configured(self) -> bool:
        return bool(settings.usajobs_api_key and settings.usajobs_email)

    def fetch(self, query: SearchQuery) -> list[FetchedJob]:
        if not self.is_configured():
            logger.info("usajobs: skipped (no USAJOBS_API_KEY/USAJOBS_EMAIL in .env)")
            return []

        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": settings.usajobs_email,
            "Authorization-Key": settings.usajobs_api_key,
        }
        params: dict = {"ResultsPerPage": min(query.max_results, 50)}
        if query.keywords:
            params["Keyword"] = " ".join(query.keywords)
        if query.location:
            params["LocationName"] = query.location
        if query.posted_within_days:
            params["DatePosted"] = min(query.posted_within_days, 60)

        data = get_json(API_URL, params=params, headers=headers)
        items = (data.get("SearchResult", {}) or {}).get("SearchResultItems", [])

        jobs: list[FetchedJob] = []
        for wrapper in items:
            d = wrapper.get("MatchedObjectDescriptor", {})
            location = ", ".join(
                loc.get("LocationName", "")
                for loc in d.get("PositionLocation", [])
            ) or d.get("PositionLocationDisplay")
            description = strip_html(
                (d.get("UserArea", {}).get("Details", {}) or {}).get("JobSummary")
                or d.get("QualificationSummary")
            )
            jobs.append(
                FetchedJob(
                    source=self.name,
                    external_id=str(d.get("PositionID", "")),
                    title=(d.get("PositionTitle") or "").strip(),
                    company=d.get("OrganizationName"),
                    country="USA",
                    location=location,
                    work_type=infer_work_type(d.get("PositionTitle"), location, description),
                    salary=_min_salary(d),
                    posted_date=_parse_date(d.get("PublicationStartDate")),
                    url=d.get("PositionURI"),
                    description=description,
                )
            )
        return jobs


def _min_salary(d: dict):
    try:
        ranges = d.get("PositionRemuneration") or []
        if ranges:
            return int(float(ranges[0].get("MinimumRange")))
    except (TypeError, ValueError, IndexError):
        pass
    return None


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None
