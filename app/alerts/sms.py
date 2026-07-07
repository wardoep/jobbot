"""
Send one SMS through whichever transport is configured.

JobBot tries them in order and uses the first that's set up:
  1. Twilio   — their HTTP API (account SID + auth token + a "from" number).
  2. dry-run  — nothing configured yet, so we just LOG the message instead of
                sending it. The pipeline still "succeeds", which lets you test
                alerts end-to-end before setting up a real Twilio account.

Which one is active is decided by settings.sms_mode (see app/config.py).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger("jobbot.alerts.sms")


@dataclass
class SmsResult:
    ok: bool
    transport: str  # "twilio" | "dry-run"
    detail: str = ""


def send_sms(to: str, text: str) -> SmsResult:
    """Send (or, in dry-run, log) one SMS. Never raises — returns a result."""
    mode = settings.sms_mode
    if mode == "twilio":
        return _send_twilio(to, text)
    return _send_dry_run(to, text)


def _send_twilio(to, text) -> SmsResult:
    url = (
        "https://api.twilio.com/2010-04-01/Accounts/"
        f"{settings.twilio_account_sid}/Messages.json"
    )
    try:
        resp = httpx.post(
            url,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            data={"From": settings.twilio_from, "To": to, "Body": text},
            timeout=30,
        )
        if resp.status_code >= 400:
            logger.warning(
                "Twilio send to %s failed: HTTP %s %s",
                to, resp.status_code, resp.text[:200],
            )
            return SmsResult(
                ok=False, transport="twilio", detail=f"HTTP {resp.status_code}"
            )
        logger.info("sent SMS to %s via Twilio", to)
        return SmsResult(ok=True, transport="twilio")
    except Exception as exc:  # noqa: BLE001 — report, don't crash the loop
        logger.warning("Twilio send to %s failed: %s", to, exc)
        return SmsResult(ok=False, transport="twilio", detail=str(exc))


def _send_dry_run(to, text) -> SmsResult:
    indented = text.replace("\n", "\n    ")
    logger.info(
        "[dry-run sms] nothing configured, so logging instead of sending "
        "(set TWILIO_* in .env and SMS_MODE=twilio to really send)\n"
        "    To: %s\n    %s",
        to, indented,
    )
    # ok=True on purpose: in dry-run a "send" is a successful log line, so the
    # match gets marked notified and the pipeline behaves exactly as it will live.
    return SmsResult(ok=True, transport="dry-run")
