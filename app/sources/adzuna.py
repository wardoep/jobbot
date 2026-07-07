"""
Adzuna adapter — https://developer.adzuna.com/

Adzuna is country-scoped via the URL path (.../jobs/us/search/1). It supports a
keyword query (`what`), a location text (`where`), and a recency cap
(`max_days_old`). Needs a free APP_ID + APP_KEY (read from .env).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.config import settings
from app.sources.base import FetchedJob, JobSource, SearchQuery, infer_work_type
from app.sources.http_util import get_json, strip_html

logger = logging.getLogger("jobbot.sources")

# Map the country names users pick to Adzuna's country codes.
COUNTRY_CODES = {
    "USA": "us", "UNITED STATES": "us", "US": "us",
    "UK": "gb", "UNITED KINGDOM": "gb", "GB": "gb",
    "CANADA": "ca", "AUSTRALIA": "au", "GERMANY": "de", "FRANCE": "fr",
    "INDIA": "in", "NETHERLANDS": "nl", "ITALY": "it", "SPAIN": "es",
    "POLAND": "pl", "BRAZIL": "br", "SINGAPORE": "sg", "NEW ZEALAND": "nz",
}


class AdzunaSource(JobSource):
    name = "adzuna"
    keyword_search = True

    def is_configured(self) -> bool:
        return bool(settings.adzuna_app_id and settings.adzuna_app_key)

    def fetch(self, query: SearchQuery) -> list[FetchedJob]:
        if not self.is_configured():
            logger.warning("adzuna: skipped (no APP_ID/APP_KEY in .env)")
            return []

        code = COUNTRY_CODES.get((query.country or "USA").upper(), "us")
        params = {
            "app_id": settings.adzuna_app_id,
            "app_key": settings.adzuna_app_key,
            "results_per_page": min(query.max_results, 50),
            "content-type": "application/json",
        }
        if query.keywords:
            params["what"] = " ".join(query.keywords)
        if query.location:
            params["where"] = query.location
        if query.posted_within_days:
            params["max_days_old"] = query.posted_within_days

        url = f"https://api.adzuna.com/v1/api/jobs/{code}/search/1"
        data = get_json(url, params=params)

        jobs: list[FetchedJob] = []
        for item in data.get("results", []):
            jobs.append(self._parse(item, query.country or "USA", code))
        return jobs

    def _parse(self, item: dict, country: str, code: str) -> FetchedJob:
        location = (item.get("location") or {}).get("display_name")
        description = strip_html(item.get("description"))
        contract_time = item.get("contract_time")  # "full_time" / "part_time"
        work_type = infer_work_type(item.get("title"), location, description)
        return FetchedJob(
            source=self.name,
            external_id=str(item.get("id", "")),
            title=item.get("title", "").strip(),
            company=(item.get("company") or {}).get("display_name"),
            country=country,
            location=location,
            work_type=work_type,
            salary=_to_int(item.get("salary_min")),
            posted_date=_parse_date(item.get("created")),
            url=item.get("redirect_url"),
            description=description,
        )


def _to_int(value) -> Optional[int]:
    try:
        return int(float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_date(value: Optional[str]):
    if not value:
        return None
    try:
        # Adzuna: "2026-06-18T12:34:56Z"
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None
