"""
The Muse adapter — https://www.themuse.com/developers/api/v2

The Muse is a well-known, reputable career site. Its public jobs API is
key-free. It has NO free-text keyword search (only category/level/location
filters), so this source runs in the base poll (keyword_search = False) and
JobBot's own gate filters the results down to each user's roles.

We request a spread of professional categories (The Muse skews tech/business;
there is no "IT" category — help-desk-style roles live under Customer Service /
Software Engineering) and let the matcher decide relevance. No salary is
provided by this API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.sources.base import FetchedJob, JobSource, SearchQuery, infer_work_type
from app.sources.http_util import get_json, strip_html

logger = logging.getLogger("jobbot.sources")

API_URL = "https://www.themuse.com/api/public/jobs"

# A field-agnostic spread of valid Muse categories (verified non-empty), so
# the source serves ANY resume — healthcare, retail, education, business,
# creative, tech — not just tech. We sample a few from EACH per poll rather
# than filling up on the first, so every field is represented.
CATEGORIES = [
    "Healthcare",
    "Business Operations",
    "Customer Service",
    "Education",
    "Sales",
    "Data and Analytics",
    "Human Resources and Recruitment",
    "Project Management",
    "Retail",
    "Design and UX",
    "Software Engineering",
    "Writing and Editing",
]


class TheMuseSource(JobSource):
    name = "themuse"
    keyword_search = False  # no free-text query param; base-poll only

    def fetch(self, query: SearchQuery) -> list[FetchedJob]:
        jobs: list[FetchedJob] = []
        seen: set[str] = set()
        # Pull page 1 of each category until we hit the cap (20 jobs/page).
        for category in CATEGORIES:
            if len(jobs) >= query.max_results:
                break
            params = {"page": 1, "category": category, "descending": "true"}
            try:
                data = get_json(API_URL, params=params)
            except Exception as exc:  # one bad category can't sink the source
                logger.info("themuse: category %r failed (%s)", category, exc)
                continue
            for item in data.get("results", []):
                ext = str(item.get("id", ""))
                if not ext or ext in seen:
                    continue
                seen.add(ext)
                job = _parse(item)
                if job is None:
                    continue
                if _too_old(job.posted_date, query.posted_within_days):
                    continue
                jobs.append(job)
                if len(jobs) >= query.max_results:
                    break
        return jobs


def _parse(item: dict):
    title = (item.get("name") or "").strip()
    if not title:
        return None
    company = (item.get("company") or {}).get("name")
    locs = [l.get("name") for l in item.get("locations", []) if l.get("name")]
    location = locs[0] if locs else None
    remote = any("remote" in (l or "").lower() or "flexible" in (l or "").lower() for l in locs)
    description = strip_html(item.get("contents"))
    return FetchedJob(
        source="themuse",
        external_id=str(item.get("id", "")),
        title=title,
        company=company,
        country=None,  # Muse gives "City, ST"; gate infers country from it
        location=location,
        work_type="Remote" if remote else infer_work_type(title, location, description),
        salary=None,  # The Muse API exposes no salary
        posted_date=_parse_date(item.get("publication_date")),
        url=(item.get("refs") or {}).get("landing_page"),
        description=description,
    )


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
    return (datetime.now(timezone.utc).date() - posted).days > within_days
