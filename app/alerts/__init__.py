"""
Alerts: turn new matches into email / Slack notifications.

The pieces:
  - email.py    : send one email (SMTP -> SendGrid -> dry-run fallback)
  - slack.py    : post to a user's Slack incoming webhook
  - compose.py  : render a user's matches into subject + bodies (no resume text)
  - notify.py   : per-user orchestration (channels, instant vs digest, mark sent)

The scheduler (app/runner.py) calls `run_alerts()` once per cycle.
"""

from __future__ import annotations

from app.alerts.email import EmailResult, send_email
from app.alerts.notify import UserAlertReport, run_alerts, send_user_alerts
from app.alerts.slack import send_slack

__all__ = [
    "send_email",
    "EmailResult",
    "send_slack",
    "send_user_alerts",
    "run_alerts",
    "UserAlertReport",
]
