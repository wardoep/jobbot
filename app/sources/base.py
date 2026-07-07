"""
The shared contract every job source must follow.

- `SearchQuery`  : what the caller wants (keywords, location, recency...).
- `FetchedJob`   : the ONE normalized shape every adapter returns.
- `JobSource`    : the interface (a base class) each adapter subclasses.

Also holds small text helpers used to normalize jobs and to build the
`dedupe_key` that lets us recognise the same job across different boards.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


# ---------------------------------------------------------------------------
# What the caller asks for. Every field is optional (blank = "any"), matching
# the user-preference philosophy. Adapters use what they can and ignore the rest.
# ---------------------------------------------------------------------------
@dataclass
class SearchQuery:
    keywords: list[str] = field(default_factory=list)
    country: Optional[str] = None  # e.g. "USA", "UK" (mapped per source)
    location: Optional[str] = None  # city / area text, for non-remote roles
    posted_within_days: Optional[int] = None
    max_results: int = 50


# ---------------------------------------------------------------------------
# The normalized job every adapter returns. Maps 1:1 onto the `jobs` table.
# ---------------------------------------------------------------------------
@dataclass
class FetchedJob:
    source: str
    external_id: str
    title: str
    company: Optional[str] = None
    country: Optional[str] = None
    location: Optional[str] = None
    work_type: Optional[str] = None  # "Remote" / "Hybrid" / "In-person"
    salary: Optional[int] = None
    posted_date: Optional[date] = None
    url: Optional[str] = None
    description: str = ""

    # --- BUILD_SPEC additions (ATS ingestion) — optional, default-safe so the
    # existing aggregator adapters that don't set them are unaffected. ----------
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    description_md: str = ""              # description normalized to Markdown
    posted_at: Optional[datetime] = None  # full timestamp (legacy posted_date = .date())
    remote_type: Optional[str] = None     # spec: remote | hybrid | onsite
    # The ATS company this came from (the runner resolves it to companies.id).
    ats_provider: Optional[str] = None    # greenhouse | lever | ashby
    ats_id: Optional[str] = None          # the company's board slug on that ATS

    @property
    def dedupe_key(self) -> str:
        return make_dedupe_key(self.title, self.company, self.location)


# ---------------------------------------------------------------------------
# The adapter interface.
# ---------------------------------------------------------------------------
class JobSource(ABC):
    #: short, stable id stored in jobs.source (e.g. "adzuna")
    name: str = "base"

    #: True for sources whose API actually SEARCHES by query.keywords (adzuna,
    #: remotive, usajobs). The runner re-polls only these for the resume-driven
    #: role searches, so scrapers/feeds aren't refetched once per term.
    keyword_search: bool = False

    def is_configured(self) -> bool:
        """Whether this source has what it needs to run (e.g. API keys).

        Sources needing no keys return True. Key-gated sources override this.
        """
        return True

    @abstractmethod
    def fetch(self, query: SearchQuery) -> list[FetchedJob]:
        """Return normalized jobs for the query. Must not raise for ordinary
        network/parse problems — return what you can (the ingester also guards).
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Shared normalization helpers
# ---------------------------------------------------------------------------
def make_dedupe_key(title: Optional[str], company: Optional[str], location: Optional[str]) -> str:
    """Build a normalized key so the SAME job from DIFFERENT boards collides.

    Lowercase, strip punctuation, collapse whitespace, drop a leading "remote"
    location noise. Title + company are the signal; location is a light tiebreak.
    """
    parts = [_norm(title), _norm(company)]
    loc = _norm(location)
    # Treat all the ways boards say "remote" as the same place.
    if loc in {"remote", "anywhere", "worldwide", "remote worldwide"}:
        loc = "remote"
    parts.append(loc)
    return "|".join(parts)


def _norm(text: Optional[str]) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


REMOTE_HINTS = ("remote", "work from home", "wfh", "anywhere", "distributed")
HYBRID_HINTS = ("hybrid", "flexible location", "partially remote")


def infer_work_type(*texts: Optional[str], remote_flag: Optional[bool] = None) -> Optional[str]:
    """Best-effort guess of Remote / Hybrid / In-person from free text.

    Some boards give an explicit remote flag (pass it as remote_flag); otherwise
    we scan the title/location/description for hints. Returns None if unsure.
    """
    if remote_flag is True:
        return "Remote"
    blob = " ".join(t.lower() for t in texts if t)
    if not blob:
        return None
    if any(h in blob for h in HYBRID_HINTS):
        return "Hybrid"
    if any(h in blob for h in REMOTE_HINTS):
        return "Remote"
    if remote_flag is False:
        return "In-person"
    return None


def matches_any_keyword(query: SearchQuery, *texts: Optional[str]) -> bool:
    """Client-side keyword filter (OR semantics) for boards lacking a search API.

    No keywords set -> everything matches (blank = "any").
    """
    if not query.keywords:
        return True
    blob = " ".join(t.lower() for t in texts if t)
    return any(kw.lower() in blob for kw in query.keywords)
