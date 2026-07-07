"""
Base class for Tier B scrapers (Phase 7).

Tier B sources are job boards with NO official API, so we read their HTML. Two
rules from the spec are baked in here so every scraper inherits them:

  1. Route EVERY request through the DataImpulse proxy (read from .env, never
     hardcoded). A scraper is only "configured" when the proxy is set.
  2. Be a polite guest: wait `crawl_delay` seconds between requests, and check
     robots.txt before fetching (a missing/unreadable robots.txt means "allowed").

Subclasses implement `fetch()`; they call `self._get_html(url)` for every request
and must stay resilient — return what they can, never crash the pipeline (the
ingester guards them too).
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from typing import Optional

from app.config import settings
from app.sources.base import JobSource
from app.sources.http_util import BROWSER_UA, get_html

logger = logging.getLogger("jobbot.sources")


class ScraperSource(JobSource):
    #: seconds to wait between requests to the same site (politeness/throttle)
    crawl_delay: float = 1.0
    #: how many times to try a request before giving up (proxies drop connections)
    max_attempts: int = 3
    #: seconds to wait between those retries
    retry_backoff: float = 1.5

    def __init__(self) -> None:
        self._last_request = 0.0
        # host -> RobotFileParser, or None meaning "no rules / allow all"
        self._robots: dict[str, Optional[RobotFileParser]] = {}

    def is_configured(self) -> bool:
        """Tier B needs the proxy; without it the source quietly sits out."""
        return settings.proxy_configured

    # -- polite, proxied fetching ------------------------------------------
    def _get_html(self, url: str, *, params: Optional[dict] = None) -> str:
        """Fetch one page through the proxy, after a robots check + throttle.

        Retries a few times on transient failures — proxied requests occasionally
        drop the TLS connection mid-handshake — before giving up.
        """
        if not self._robots_allows(url):
            raise PermissionError(f"robots.txt disallows {url}")
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_attempts):
            self._wait_turn()
            try:
                return get_html(url, params=params, proxy=settings.proxy_for_requests)
            except Exception as exc:  # noqa: BLE001 — retry transient proxy/network drops
                last_exc = exc
                if attempt < self.max_attempts - 1:
                    logger.info("scraper: retry %d for %s (%s)",
                                attempt + 1, url, type(exc).__name__)
                    time.sleep(self.retry_backoff)
        assert last_exc is not None
        raise last_exc

    def _wait_turn(self) -> None:
        gap = self.crawl_delay - (time.monotonic() - self._last_request)
        if gap > 0:
            time.sleep(gap)
        self._last_request = time.monotonic()

    # -- robots.txt (best effort) ------------------------------------------
    def _robots_allows(self, url: str) -> bool:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            self._robots[host] = self._load_robots(host)
        rp = self._robots[host]
        if rp is None:
            return True  # no robots.txt (or unreadable) -> allowed
        try:
            return rp.can_fetch(BROWSER_UA, url)
        except Exception:  # noqa: BLE001 — never let a robots quirk block us
            return True

    def _load_robots(self, host: str) -> Optional[RobotFileParser]:
        try:
            text = get_html(host + "/robots.txt", proxy=settings.proxy_for_requests)
        except Exception:  # noqa: BLE001 — 404 / blocked / network -> allow all
            return None
        rp = RobotFileParser()
        rp.parse(text.splitlines())
        return rp
