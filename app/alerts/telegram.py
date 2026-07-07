"""
Telegram alert transport.

Sends messages from the app's bot (TELEGRAM_BOT_TOKEN in .env) to a user's
private chat (User.telegram_chat_id, linked on the Options page). Follows the
same per-user privacy rule as Slack: a message only ever goes to the chat ID
stored on THAT user's row, so alerts can't leak to someone else.

Dry-run friendly: with no token configured, sends are skipped and logged.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger("jobbot.alerts")

_API = "https://api.telegram.org/bot{token}/{method}"


def telegram_configured() -> bool:
    return bool(settings.telegram_bot_token.strip())


def send_telegram(chat_id: str, text: str) -> bool:
    """Send an HTML-formatted message; True on success. Never raises."""
    if not telegram_configured():
        logger.info("telegram: skipped (no TELEGRAM_BOT_TOKEN in .env)")
        return False
    if not (chat_id or "").strip():
        return False
    try:
        resp = httpx.post(
            _API.format(token=settings.telegram_bot_token.strip(), method="sendMessage"),
            json={
                "chat_id": chat_id,
                "text": text[:4000],  # Telegram caps messages at 4096 chars
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        ok = resp.status_code == 200 and resp.json().get("ok") is True
        if not ok:
            logger.warning("telegram send failed: %s %s", resp.status_code, resp.text[:200])
        return ok
    except Exception as exc:  # noqa: BLE001 — alerting must never crash a cycle
        logger.warning("telegram send error: %s", exc)
        return False


def get_updates() -> list[dict]:
    """Recent messages sent to the bot (for the Options link flow). Never raises."""
    if not telegram_configured():
        return []
    try:
        resp = httpx.get(
            _API.format(token=settings.telegram_bot_token.strip(), method="getUpdates"),
            timeout=15,
        )
        data = resp.json()
        return data.get("result", []) if data.get("ok") else []
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram getUpdates error: %s", exc)
        return []
