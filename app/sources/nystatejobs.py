"""
StateJobsNY scraper — https://statejobsny.com (Tier B, Phase 7).

New York State's official jobs board has no API, so we read its HTML (through the
DataImpulse proxy, like every Tier B source). Two steps:

  1. `vacancyTable.cfm` lists ALL current vacancies in one server-rendered table
     (Item #, Title, Grade, Posted, Deadline, Agency, County). We fetch it once and
     filter by keyword + recency ourselves.
  2. For the rows that pass (up to `max_results`), we fetch each
     `vacancyDetailsView.cfm?id=...` page to add the duties description, employment
     type, and city. Detail fetches are throttled and bounded, and any single
     failure just leaves that job with its table-level info.

Resilience: we parse the table by COLUMN NAME (not fixed positions), and every
network/parse problem is caught — the scraper returns what it has, never crashing
the run. If the layout changes a lot, you'll see fewer/thinner jobs, not a crash.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

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

BASE = "https://statejobsny.com/public/"
LIST_URL = BASE + "vacancyTable.cfm"


class NYStateJobsSource(ScraperSource):
    name = "nystatejobs"
    crawl_delay = 1.0  # be a polite guest on a government site

    def fetch(self, query: SearchQuery) -> list[FetchedJob]:
        try:
            html = self._get_html(LIST_URL)
        except Exception as exc:  # noqa: BLE001 — listing unreachable -> nothing
            logger.warning("nystatejobs: could not load the vacancy list: %s", exc)
            return []

        rows = _parse_table(html)
        if not rows:
            logger.warning("nystatejobs: vacancy table missing or empty (layout change?)")
            return []

        # Layer the cheap filters first so we only fetch detail pages we'll keep.
        survivors = []
        for row in rows:
            if not matches_any_keyword(query, row["title"], row["agency"], row["county"]):
                continue
            if _too_old(row["posted"], query.posted_within_days):
                continue
            survivors.append(row)
            if len(survivors) >= query.max_results:
                break

        jobs: list[FetchedJob] = []
        for row in survivors:
            jobs.append(self._build_job(row))
        return jobs

    # -- one vacancy -------------------------------------------------------
    def _build_job(self, row: dict) -> FetchedJob:
        job_id = row["item"]
        url = (urljoin(BASE, row["href"]) if row["href"]
               else f"{BASE}vacancyDetailsView.cfm?id={job_id}")
        county = row["county"]
        location = f"{county}, NY" if county else "NY"
        work_type = None
        employment_type = None
        duties = ""

        # Enrich from the detail page; on any failure keep the table-level job.
        try:
            detail = self._get_html(f"{BASE}vacancyDetailsView.cfm?id={job_id}")
            text = _flatten(detail)
            duties = _section(
                text,
                ["Duties Description", "Minimum Qualifications"],
                ["How to Apply", "Notes on Applying", "Some positions",
                 "Additional Comments", "Contact Information", "For more information",
                 "Click here"],
            )
            employment_type = _employment_type(text)
            city = _city(text)
            if city:
                location = f"{city}, NY"
            work_type = infer_work_type(row["title"], duties)
        except Exception as exc:  # noqa: BLE001 — keep the table-level job
            logger.info("nystatejobs: detail %s unavailable (%s); using listing info",
                        job_id, type(exc).__name__)

        # Description = duties first (best matching signal), then structured facts.
        # We spell out the employment type so the gate's text-based filter reads it.
        facts = [b for b in [
            f"Agency: {row['agency']}" if row["agency"] else "",
            f"County: {county}" if county else "",
            f"Salary grade: {row['grade']}" if row["grade"] else "",
            f"Employment type: {employment_type}" if employment_type else "",
            f"Application deadline: {row['deadline']}" if row["deadline"] else "",
        ] if b]
        description = "\n\n".join(p for p in [duties[:4000], ". ".join(facts)] if p).strip()

        return FetchedJob(
            source=self.name,
            external_id=str(job_id),
            title=row["title"],
            company=row["agency"] or "New York State",
            country="USA",
            location=location,
            work_type=work_type,
            salary=None,  # NY posts salary GRADES, not reliable numbers
            posted_date=row["posted"],
            url=url,
            description=description,
        )


# ---------------------------------------------------------------------------
# Parsing helpers (kept text-based so small layout tweaks don't break them)
# ---------------------------------------------------------------------------
_HEADER_MAP = [
    ("item", ("item",)),
    ("title", ("title",)),
    ("grade", ("grade",)),
    ("posted", ("post",)),
    ("deadline", ("deadline",)),
    ("agency", ("agency",)),
    ("county", ("county",)),
]


def _parse_table(html: str) -> list[dict]:
    """Return one dict per vacancy row, keyed by column name (not position)."""
    try:
        doc = lxml.html.fromstring(html)
    except Exception:  # noqa: BLE001
        return []
    tables = doc.xpath('//table[@id="vacancyTable"]') or doc.xpath("//table")
    if not tables:
        return []
    table = tables[0]
    trs = table.xpath(".//tr")
    if len(trs) < 2:
        return []

    header_cells = trs[0].xpath("./th|./td")
    col = {}
    for i, cell in enumerate(header_cells):
        h = _norm(cell.text_content())
        for key, needles in _HEADER_MAP:
            if key not in col and any(n in h for n in needles):
                col[key] = i

    rows: list[dict] = []
    for tr in trs[1:]:
        tds = tr.xpath("./td")
        if not tds:
            continue

        def cell(name: str) -> str:
            i = col.get(name)
            return tds[i].text_content().strip() if i is not None and i < len(tds) else ""

        hrefs = tr.xpath(".//a[@href]")
        href = hrefs[0].get("href") if hrefs else None
        item = cell("item") or _id_from_href(href)
        title = cell("title")
        if not (item and title):
            continue
        rows.append({
            "item": item,
            "title": title,
            "grade": cell("grade"),
            "posted": _parse_date(cell("posted")),
            "deadline": cell("deadline"),
            "agency": cell("agency"),
            "county": cell("county"),
            "href": href,
        })
    return rows


def _flatten(html: str) -> str:
    try:
        text = lxml.html.fromstring(html).text_content()
    except Exception:  # noqa: BLE001
        text = strip_html(html)
    return re.sub(r"\s+", " ", text).strip()


def _section(text: str, starts: list[str], ends: list[str]) -> str:
    """Slice `text` from the first start label to the earliest following end label."""
    lo = -1
    for s in starts:
        i = text.find(s)
        if i != -1:
            lo = i + len(s)
            break
    if lo == -1:
        return ""
    hi = len(text)
    for e in ends:
        j = text.find(e, lo)
        if j != -1:
            hi = min(hi, j)
    return text[lo:hi].strip(" :.-")


def _employment_type(text: str) -> Optional[str]:
    m = re.search(r"Employment Type\s*([A-Za-z\-/ ]{3,20})", text)
    if not m:
        return None
    val = m.group(1).lower()
    if "full" in val:
        return "full-time"
    if "part" in val:
        return "part-time"
    if "season" in val or "temp" in val:
        return "contract"
    return None


def _city(text: str) -> Optional[str]:
    m = re.search(r"\bCity\s+(.+?)\s+State\b", text)
    if m:
        city = m.group(1).strip()
        if 0 < len(city) <= 40:
            return city
    return None


def _id_from_href(href: Optional[str]) -> str:
    if not href:
        return ""
    m = re.search(r"id=(\d+)", href)
    return m.group(1) if m else ""


def _parse_date(value: str):
    value = (value or "").strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _too_old(posted, within_days) -> bool:
    if posted is None or not within_days:
        return False
    return (datetime.now(timezone.utc).date() - posted).days > within_days


def _norm(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
