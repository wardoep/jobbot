"""
Post a message to a user's Slack "Incoming Webhook".

Each user stores their OWN webhook URL in preferences, so one person's matches
are never delivered to someone else's channel. If a user turned on the Slack
channel but hasn't pasted a webhook yet, the caller simply skips Slack for them.

Setting up a webhook (one-time, per user): in Slack, create an app with
"Incoming Webhooks" enabled, add it to a channel, and copy the webhook URL
(looks like https://hooks.slack.com/services/T000/B000/xxxx).
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("jobbot.alerts.slack")


def send_slack(webhook_url: str, text: str) -> bool:
    """POST a simple message to a Slack webhook. Returns True on success."""
    try:
        resp = httpx.post(webhook_url, json={"text": text}, timeout=30)
        if resp.status_code >= 400:
            logger.warning(
                "Slack webhook failed: HTTP %s %s",
                resp.status_code, resp.text[:200],
            )
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — never break the alert loop
        logger.warning("Slack webhook error: %s", exc)
        return False
