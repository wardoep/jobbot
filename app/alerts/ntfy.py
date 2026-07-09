"""
Send one push notification via ntfy (https://ntfy.sh) — the simple
pub/sub notification app. The user subscribes to a topic in the ntfy app;
JobBot POSTs a message to that topic. No account or key needed for public
topics on ntfy.sh; self-hosted servers work by saving a full URL instead
of a bare topic name.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("jobbot.alerts.ntfy")


def _topic_url(topic_or_url: str) -> str:
    t = (topic_or_url or "").strip()
    if t.startswith(("http://", "https://")):
        return t.rstrip("/")
    return f"https://ntfy.sh/{t}"


def send_ntfy(topic_or_url: str, title: str, text: str) -> bool:
    """POST one notification. Returns False (and logs) on any failure."""
    if not (topic_or_url or "").strip():
        return False
    url = _topic_url(topic_or_url)
    try:
        resp = httpx.post(
            url,
            content=(text or "").encode("utf-8"),
            headers={
                # ntfy requires header values to be latin-1; keep the title ASCII-safe
                "Title": (title or "JobBot").encode("ascii", "ignore").decode() or "JobBot",
                "Tags": "briefcase",
            },
            timeout=15,
        )
        if resp.status_code >= 400:
            logger.warning("ntfy post to %s failed: HTTP %s %s",
                           url, resp.status_code, resp.text[:150])
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — report, don't crash the caller
        logger.warning("ntfy post to %s failed: %s", url, exc)
        return False
