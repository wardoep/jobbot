"""
JSearch adapter — https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch

JSearch returns Google-for-Jobs results, which include postings from Indeed,
LinkedIn, Glassdoor, ZipRecruiter and employer career pages — the boards that
have no public APIs of their own. Key-gated: set JSEARCH_API_KEY in .env
(create a free account at rapidapi.com, subscribe to the JSearch free tier,
copy the X-RapidAPI-Key). Without the key this source cleanly skips itself.

The free tier allows a limited number of searches per month, so this adapter
is keyword_search-only in spirit: with no keywords there's nothing sensible
to ask Google for, so it returns nothing rather than burn quota on noise.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.config import settings
from app.sources.base import FetchedJob, JobSource, SearchQuery, infer_work_type
from app.sources.http_util import get_json, strip_html

logger = logging.getLogger("jobbot.sources")

API_URL = "https://jsearch.p.rapidapi.com/search-v2"

# JSearch country codes it supports for the `country` param.
COUNTRY_CODES = {
    "USA": "us", "UNITED STATES": "us", "US": "us",
    "CANADA": "ca", "UK": "gb", "UNITED KINGDOM": "gb",
    "GERMANY": "de", "AUSTRALIA": "au", "INDIA": "in",
}


class JSearchSource(JobSource):
    name = "jsearch"
    keyword_search = True

    def is_configured(self) -> bool:
        return bool(settings.jsearch_api_key.strip())

    def fetch(self, query: SearchQuery) -> list[FetchedJob]:
        if not self.is_configured():
            logger.info("jsearch: skipped (no JSEARCH_API_KEY in .env)")
            return []
        if not query.keywords:
            return []  # don't spend quota on an unscoped search

        # Hard monthly cap: self-skip once the free-tier budget is spent, so
        # JSearch can never run up a bill no matter how often it's polled.
        from app.db import Session
        from app.source_budget import try_spend

        with Session() as budget_session:
            if not try_spend(budget_session, "jsearch", settings.jsearch_monthly_cap):
                logger.info("jsearch: monthly request cap reached — skipping until next month")
                return []

        what = " ".join(query.keywords)
        q = f"{what} in {query.location}" if query.location else what
        params: dict = {
            "query": q,
            "num_pages": 1,
            "country": COUNTRY_CODES.get((query.country or "USA").upper(), "us"),
        }
        if query.posted_within_days:
            params["date_posted"] = (
                "today" if query.posted_within_days <= 1
                else "3days" if query.posted_within_days <= 3
                else "week" if query.posted_within_days <= 7
                else "month"
            )
        headers = {
            "X-RapidAPI-Key": settings.jsearch_api_key.strip(),
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
        data = get_json(API_URL, params=params, headers=headers)

        # /search-v2 nests the list under data.jobs (older /search returned a
        # bare data list); tolerate both shapes.
        payload = data.get("data")
        items = payload.get("jobs", []) if isinstance(payload, dict) else (payload or [])

        jobs: list[FetchedJob] = []
        for item in items[: query.max_results]:
            title = (item.get("job_title") or "").strip()
            if not title:
                continue
            city = item.get("job_city") or ""
            state = item.get("job_state") or ""
            location = ", ".join(x for x in [city, state] if x) or None
            remote = bool(item.get("job_is_remote"))
            description = strip_html(item.get("job_description"))
            jobs.append(
                FetchedJob(
                    source=self.name,
                    external_id=str(item.get("job_id", "")),
                    title=title,
                    company=item.get("employer_name"),
                    country=item.get("job_country"),
                    location=location,
                    work_type="Remote" if remote else infer_work_type(title, location, description),
                    salary=_num(item.get("job_min_salary")),
                    salary_min=_num(item.get("job_min_salary")),
                    salary_max=_num(item.get("job_max_salary")),
                    salary_currency=(item.get("job_salary_currency") or None),
                    posted_date=_parse_date(item.get("job_posted_at_datetime_utc")),
                    url=item.get("job_apply_link"),
                    description=description,
                )
            )
        return jobs


def _num(val):
    try:
        return int(val) if val else None
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None
