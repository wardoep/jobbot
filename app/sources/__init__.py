"""
Job-source adapters.

Every job board is wrapped in an "adapter" that exposes the SAME `fetch()`
method and returns the SAME normalized `FetchedJob` shape. The rest of the app
never knows or cares which board a job came from. If one adapter breaks, the
ingestion loop logs it and keeps going (see app/ingest.py).

`ENABLED_SOURCES` is the registry the ingester walks. It's split into tiers:
  - Tier A — official APIs (Phase 2), key-gated where needed.
  - Tier B — HTML scrapers via the DataImpulse proxy (Phase 7). These self-skip
    when the proxy isn't configured (their `is_configured()` checks for it).
To add a source, write an adapter and add it to the right tier below.
"""

from __future__ import annotations

from app.sources.adzuna import AdzunaSource
from app.sources.arbeitnow import ArbeitnowSource
from app.sources.base import FetchedJob, JobSource, SearchQuery
from app.sources.ctstatejobs import CTStateJobsSource
from app.sources.jsearch import JSearchSource
from app.sources.nystatejobs import NYStateJobsSource
from app.sources.remoteok import RemoteOKSource
from app.sources.remotive import RemotiveSource
from app.sources.themuse import TheMuseSource
from app.sources.usajobs import USAJobsSource

# Tier A — official APIs. Order doesn't matter; each runs independently.
TIER_A_SOURCES: list[JobSource] = [
    AdzunaSource(),
    RemotiveSource(),
    RemoteOKSource(),
    ArbeitnowSource(),
    USAJobsSource(),
    TheMuseSource(),  # reputable, keyless; base-poll only (no keyword search)
    JSearchSource(),  # Google-for-Jobs (Indeed/LinkedIn/Glassdoor postings); needs JSEARCH_API_KEY
]

# Tier B — scrapers routed through the proxy (skip themselves without it).
TIER_B_SOURCES: list[JobSource] = [
    NYStateJobsSource(),
    CTStateJobsSource(),
]

ENABLED_SOURCES: list[JobSource] = TIER_A_SOURCES + TIER_B_SOURCES

__all__ = [
    "FetchedJob",
    "JobSource",
    "SearchQuery",
    "TIER_A_SOURCES",
    "TIER_B_SOURCES",
    "ENABLED_SOURCES",
]
