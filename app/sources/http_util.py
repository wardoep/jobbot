"""
Tiny shared helpers for the adapters: a guarded JSON GET and an HTML stripper.

`get_json` always applies a timeout and a polite User-Agent, and raises on HTTP
errors so each adapter can decide how to react. Adapters wrap their own calls in
try/except, and the ingester wraps the whole adapter again — defence in depth so
one flaky board never crashes the run.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

logger = logging.getLogger("jobbot.sources")

USER_AGENT = "JobBot/0.1 (+https://example.com; job-search aggregator)"
# Some sites refuse a non-browser User-Agent, so the Tier B scrapers (Phase 7)
# present a normal desktop-browser string instead.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
# Scrapers can be slower (proxy + big pages), so they get a longer ceiling.
SCRAPER_TIMEOUT = httpx.Timeout(45.0, connect=15.0)


def get_json(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    proxy: Optional[str] = None,
) -> Any:
    """GET a URL and parse JSON. Raises on network/HTTP errors."""
    merged_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        merged_headers.update(headers)
    client_kwargs: dict[str, Any] = {
        "timeout": DEFAULT_TIMEOUT,
        "follow_redirects": True,
    }
    if proxy:
        client_kwargs["proxy"] = proxy
    with httpx.Client(**client_kwargs) as client:
        resp = client.get(url, params=params, headers=merged_headers)
        resp.raise_for_status()
        return resp.json()


def get_html(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    proxy: Optional[str] = None,
    timeout: Optional[httpx.Timeout] = None,
) -> str:
    """GET a URL and return its text (HTML). Raises on network/HTTP errors.

    Used by the Tier B scrapers, which pass the DataImpulse proxy. A real
    browser User-Agent is sent by default so picky sites don't refuse us.
    """
    merged_headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if headers:
        merged_headers.update(headers)
    client_kwargs: dict[str, Any] = {
        "timeout": timeout or SCRAPER_TIMEOUT,
        "follow_redirects": True,
    }
    if proxy:
        client_kwargs["proxy"] = proxy
    with httpx.Client(**client_kwargs) as client:
        resp = client.get(url, params=params, headers=merged_headers)
        resp.raise_for_status()
        return resp.text


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: Optional[str]) -> str:
    """Turn an HTML job description into plain text for matching/storage."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    # Decode the few entities that show up most often.
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"')):
        text = text.replace(entity, char)
    return _WS_RE.sub(" ", text).strip()
