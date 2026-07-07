"""
Connecticut state-jobs scraper — https://www.jobapscloud.com/CT (Tier B, Phase 7).

Connecticut posts its state jobs on the JobAps platform, which has no API, so we
read its HTML through the DataImpulse proxy (like every Tier B source). Two steps,
mirroring the nystatejobs adapter:

  1. The /CT/ page is a server-rendered list of every current opening, each linking
     to a `bulpreview.asp?R1=...&R2=...&R3=...` detail page. We fetch it once and
     keyword-filter ourselves.
  2. For the rows that pass (up to `max_results`), we fetch the detail page and read
     its embedded schema.org JSON-LD `JobPosting` — datePosted, description, salary,
     employment type, hiring org, location — which is cleaner and more stable than
     scraping visible labels. Recency is filtered here, because the list shows only a
     close date, not a posted date.

Resilience: a missing list, an unreachable detail page, or absent JSON-LD each
degrade gracefully (we keep what we have); nothing raises (the ingester guards us
too). jobapscloud.com has no robots.txt, so the ScraperSource robots check allows us.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, urljoin, urlsplit

import lxml.html

from app.sources.base import (
    FetchedJob,
    SearchQuery,
    infer_work_type,
    matches_any_keyword,
)
from app.sources.http_util import strip_html
from app.sources.scraper_base import ScraperSource

logger = logging.getLogger("jobbot.sources")

BASE = "https://www.jobapscloud.com/CT/"
LIST_URL = BASE  # the /CT/ landing page IS the current-openings list

# Rows that aren't real vacancies (perpetual application templates / help entries).
_SKIP_TITLES = ("master application", "freenames")


class CTStateJobsSource(ScraperSource):
    name = "ctstatejobs"
    crawl_delay = 1.0  # be a polite guest on a government site

    def fetch(self, query: SearchQuery) -> list[FetchedJob]:
        try:
            html = self._get_html(LIST_URL)
        except Exception as exc:  # noqa: BLE001 — list unreachable -> nothing
            logger.warning("ctstatejobs: could not load the job list: %s", exc)
            return []

        rows = _parse_list(html)
        if not rows:
            logger.warning("ctstatejobs: job list empty (layout change?)")
            return []

        # Cheap keyword filter first, so we only fetch detail pages we might keep.
        survivors = []
        for row in rows:
            if not matches_any_keyword(query, row["title"], row["rowtext"]):
                continue
            survivors.append(row)
            if len(survivors) >= query.max_results:
                break

        jobs: list[FetchedJob] = []
        for row in survivors:
            job = self._build_job(row, query.posted_within_days)
            if job is not None:
                jobs.append(job)
        return jobs

    # -- one vacancy -------------------------------------------------------
    def _build_job(self, row: dict, within_days: Optional[int]) -> Optional[FetchedJob]:
        posting: dict = {}
        try:
            posting = _extract_jobposting(self._get_html(row["url"])) or {}
        except Exception as exc:  # noqa: BLE001 — keep the list-level job
            logger.info("ctstatejobs: detail for %s unavailable (%s); using list info",
                        row["external_id"], type(exc).__name__)

        posted = _iso_date(posting.get("datePosted"))
        # Recency lives on the detail page (the list has only a close date).
        if posted is not None and _too_old(posted, within_days):
            return None

        title = (posting.get("title") or row["title"]).strip()
        company = _org_name(posting) or "State of Connecticut"
        location = _location(posting) or "CT"
        employment = _employment_type(posting)
        deadline = _iso_date_or_text(posting.get("validThrough"))
        duties = strip_html(posting.get("description") or "")[:6000]

        # Spell out employment type in the text so the gate's filter can read it
        # (FetchedJob has no employment_type field — same approach as nystatejobs).
        facts = [b for b in [
            f"Agency: {company}",
            f"Location: {location}",
            f"Employment type: {employment}" if employment else "",
            f"Application deadline: {deadline}" if deadline else "",
        ] if b]
        description = "\n\n".join(p for p in [duties, ". ".join(facts)] if p).strip()

        return FetchedJob(
            source=self.name,
            external_id=row["external_id"],
            title=title,
            company=company,
            country="USA",
            location=location,
            work_type=infer_work_type(title, duties),
            salary=_salary(posting),
            posted_date=posted,
            url=row["url"],
            description=description,
        )


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def _parse_list(html: str) -> list[dict]:
    """One dict per opening: title, detail url, external_id, and row text."""
    try:
        doc = lxml.html.fromstring(html)
    except Exception:  # noqa: BLE001
        return []
    rows: list[dict] = []
    seen: set[str] = set()
    for a in doc.xpath('//a[contains(@href, "bulpreview")]'):
        href = a.get("href")
        title = (a.text_content() or "").strip()
        if not href or not title:
            continue
        if any(s in title.lower() for s in _SKIP_TITLES):
            continue
        ext = _external_id(href)
        if not ext or ext in seen:  # the same job is listed under several categories
            continue
        seen.add(ext)
        tr = a.xpath("ancestor::tr[1]")
        rowtext = re.sub(r"\s+", " ", tr[0].text_content()).strip() if tr else title
        rows.append({
            "title": title,
            "url": urljoin(BASE, href),
            "external_id": ext,
            "rowtext": rowtext,
        })
    return rows


def _external_id(href: str) -> str:
    """Stable id from the bulpreview R1/R2/R3 query parts, e.g. 260615-3591CL-001."""
    q = parse_qs(urlsplit(href).query)
    parts = [q.get(k, [""])[0].strip() for k in ("R1", "R2", "R3")]
    return "-".join(p for p in parts if p)


def _extract_jobposting(html: str) -> Optional[dict]:
    """Return the schema.org JSON-LD JobPosting object from the detail page, if any."""
    for block in re.findall(
        r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I
    ):
        try:
            data = json.loads(block.strip())
        except (ValueError, TypeError):
            continue
        for obj in _iter_jsonld(data):
            if isinstance(obj, dict) and obj.get("@type") == "JobPosting":
                return obj
    return None


def _iter_jsonld(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld(item)
    elif isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _iter_jsonld(item)
        yield data


def _org_name(posting: dict) -> Optional[str]:
    org = posting.get("hiringOrganization")
    if isinstance(org, dict):
        name = org.get("name")
        return name.strip() if isinstance(name, str) and name.strip() else None
    return org.strip() if isinstance(org, str) and org.strip() else None


def _location(posting: dict) -> Optional[str]:
    loc = posting.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, dict):
        addr = loc.get("address")
        if isinstance(addr, dict):
            city = (addr.get("addressLocality") or "").strip()
            region = (addr.get("addressRegion") or "").strip()
            parts = [p for p in (city, region) if p]
            if parts:
                return ", ".join(parts)
    return None


def _salary(posting: dict) -> Optional[int]:
    sal = posting.get("baseSalary")
    if not isinstance(sal, dict):
        return None
    val = sal.get("value")
    if isinstance(val, dict):
        for key in ("minValue", "value"):
            num = _to_int(val.get(key))
            if num:
                return num
        return None
    return _to_int(val)


def _to_int(value) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _employment_type(posting: dict) -> Optional[str]:
    et = posting.get("employmentType")
    if isinstance(et, list):
        et = et[0] if et else None
    if not isinstance(et, str):
        return None
    low = et.lower()
    if "full" in low:
        return "full-time"
    if "part" in low:
        return "part-time"
    if "contract" in low or "temp" in low:
        return "contract"
    if "intern" in low:
        return "internship"
    return None


def _iso_date(value) -> Optional[date]:
    if not isinstance(value, str):
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value.strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _iso_date_or_text(value) -> str:
    d = _iso_date(value)
    if d:
        return d.isoformat()
    return value.strip() if isinstance(value, str) else ""


def _too_old(posted: date, within_days: Optional[int]) -> bool:
    if posted is None or not within_days:
        return False
    return (datetime.now(timezone.utc).date() - posted).days > within_days
