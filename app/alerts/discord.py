"""
Send one message to a Discord channel via an incoming webhook.

The user creates the webhook themselves (their server → channel settings →
Integrations → Webhooks → New Webhook → Copy URL) and pastes the URL into
JobBot. Only real Discord webhook URLs are accepted, so a typo can't make
JobBot POST private updates to some random site.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("jobbot.alerts.discord")

_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
)


def valid_webhook(url: str) -> bool:
    return (url or "").strip().startswith(_PREFIXES)


def send_discord(webhook_url: str, content: str) -> bool:
    """POST one message. Returns False (and logs) on any failure."""
    url = (webhook_url or "").strip()
    if not valid_webhook(url):
        return False
    try:
        resp = httpx.post(url, json={"content": (content or "")[:1900]}, timeout=15)
        if resp.status_code >= 400:
            logger.warning("discord webhook post failed: HTTP %s %s",
                           resp.status_code, resp.text[:150])
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — report, don't crash the caller
        logger.warning("discord webhook post failed: %s", exc)
        return False
