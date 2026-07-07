"""
Send one email through whichever transport is configured.

JobBot tries them in order and uses the first that's set up:
  1. Resend    — their HTTP API (RESEND_API_KEY); sends from your verified domain.
  2. SMTP      — Python's built-in mail client (Gmail, Fastmail, your server...).
  3. SendGrid  — their HTTP API, if you'd rather use a key than SMTP.
  4. dry-run   — nothing configured yet, so we just LOG the email instead of
                 sending it. The pipeline still "succeeds", which lets you test
                 alerts end-to-end before setting up a real mail account.

Which one is active is decided by settings.email_mode (see app/config.py).
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger("jobbot.alerts.email")


@dataclass
class EmailResult:
    ok: bool
    transport: str  # "smtp" | "sendgrid" | "dry-run"
    detail: str = ""


def send_email(
    to: str, subject: str, text_body: str, html_body: Optional[str] = None
) -> EmailResult:
    """Send (or, in dry-run, log) one email. Never raises — returns a result."""
    mode = settings.email_mode
    if mode == "resend":
        return _send_resend(to, subject, text_body, html_body)
    if mode == "smtp":
        return _send_smtp(to, subject, text_body, html_body)
    if mode == "sendgrid":
        return _send_sendgrid(to, subject, text_body, html_body)
    return _send_dry_run(to, subject, text_body)


def _build_message(to, subject, text_body, html_body) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.email_sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text_body)  # plain-text part (always present)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    return msg


def _send_smtp(to, subject, text_body, html_body) -> EmailResult:
    msg = _build_message(to, subject, text_body, html_body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("sent email to %s via SMTP — %s", to, subject)
        return EmailResult(ok=True, transport="smtp")
    except Exception as exc:  # noqa: BLE001 — report, don't crash the loop
        logger.warning("SMTP send to %s failed: %s", to, exc)
        return EmailResult(ok=False, transport="smtp", detail=str(exc))


def _send_sendgrid(to, subject, text_body, html_body) -> EmailResult:
    content = [{"type": "text/plain", "value": text_body}]
    if html_body:
        content.append({"type": "text/html", "value": html_body})
    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": settings.email_sender},
        "subject": subject,
        "content": content,
    }
    try:
        resp = httpx.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
            json=payload,
            timeout=30,
        )
        if resp.status_code >= 400:
            logger.warning(
                "SendGrid send to %s failed: HTTP %s %s",
                to, resp.status_code, resp.text[:200],
            )
            return EmailResult(
                ok=False, transport="sendgrid", detail=f"HTTP {resp.status_code}"
            )
        logger.info("sent email to %s via SendGrid — %s", to, subject)
        return EmailResult(ok=True, transport="sendgrid")
    except Exception as exc:  # noqa: BLE001
        logger.warning("SendGrid send to %s failed: %s", to, exc)
        return EmailResult(ok=False, transport="sendgrid", detail=str(exc))


def _send_resend(to, subject, text_body, html_body) -> EmailResult:
    """Send via the Resend API (https://resend.com) from the verified domain.

    Only the delivery changes — the code/subject/body handed in are untouched.
    """
    payload = {
        "from": settings.resend_from,
        "to": [to],
        "subject": subject,
        "text": text_body,
    }
    if html_body:
        payload["html"] = html_body
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json=payload,
            timeout=30,
        )
        if resp.status_code >= 400:
            logger.warning(
                "Resend send to %s failed: HTTP %s %s",
                to, resp.status_code, resp.text[:200],
            )
            return EmailResult(
                ok=False, transport="resend", detail=f"HTTP {resp.status_code}"
            )
        logger.info("sent email to %s via Resend — %s", to, subject)
        return EmailResult(ok=True, transport="resend")
    except Exception as exc:  # noqa: BLE001 — report, don't crash the caller
        logger.warning("Resend send to %s failed: %s", to, exc)
        return EmailResult(ok=False, transport="resend", detail=str(exc))


def _send_dry_run(to, subject, text_body) -> EmailResult:
    indented = text_body.replace("\n", "\n    ")
    logger.info(
        "[dry-run email] nothing configured, so logging instead of sending "
        "(set SMTP_* or SENDGRID_API_KEY in .env to really send)\n"
        "    To: %s\n    Subject: %s\n    %s",
        to, subject, indented,
    )
    # ok=True on purpose: in dry-run a "send" is a successful log line, so the
    # match gets marked notified and the pipeline behaves exactly as it will live.
    return EmailResult(ok=True, transport="dry-run")
