"""
A tiny in-memory rate limiter for the login form, to slow down password-guessing
bots once the site is on the public internet.

It is deliberately simple: we remember the times of recent *failed* logins per
visitor IP, and once there are too many within a short window we make that IP wait.
A real person who mistypes a couple of times is never affected. This is not meant
to stop a determined, IP-rotating attacker on its own — Cloudflare sits in front for
that — it just makes blind brute-forcing impractical.

Because the app runs behind Cloudflare, the visitor's real IP arrives in the
``CF-Connecting-IP`` header (the raw socket is always 127.0.0.1, the tunnel).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request

# Tunables: allow this many failures within the window before blocking.
_WINDOW_SECONDS = 600  # 10 minutes
_MAX_FAILURES = 8  # generous, so normal mistypes never lock anyone out

# IP -> timestamps of recent failed logins.
_failures: dict[str, deque[float]] = defaultdict(deque)

# Separate cap for *verification SMS sends* (2FA enrollment). The enrollment
# endpoint texts a code to a user-supplied number, so without a hard ceiling an
# authenticated user could loop it to bomb an arbitrary victim number / run up a
# Twilio bill. Kept apart from the login-failure counter so the two never
# interfere, and intentionally tight (a real person needs only one or two).
_SMS_WINDOW_SECONDS = 3600  # 1 hour
_MAX_SMS_SENDS = 5  # per IP, per hour
_sms_sends: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    """The real visitor IP — from Cloudflare's header when present."""
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _recent(ip: str, now: float) -> deque[float]:
    """Drop timestamps older than the window; tidy up empty entries."""
    dq = _failures[ip]
    while dq and now - dq[0] > _WINDOW_SECONDS:
        dq.popleft()
    if not dq:
        _failures.pop(ip, None)
    return dq


def login_blocked(request: Request) -> bool:
    """True if this visitor has too many recent failed logins."""
    now = time.time()
    return len(_recent(_client_ip(request), now)) >= _MAX_FAILURES


def record_failed_login(request: Request) -> None:
    now = time.time()
    ip = _client_ip(request)
    _recent(ip, now)
    _failures[ip].append(now)


def clear_failed_logins(request: Request) -> None:
    """Wipe the counter for this visitor (call on a successful login)."""
    _failures.pop(_client_ip(request), None)


def _recent_sms(ip: str, now: float) -> deque[float]:
    """Drop SMS-send timestamps older than the window; tidy up empty entries."""
    dq = _sms_sends[ip]
    while dq and now - dq[0] > _SMS_WINDOW_SECONDS:
        dq.popleft()
    if not dq:
        _sms_sends.pop(ip, None)
    return dq


def sms_send_blocked(request: Request) -> bool:
    """True if this visitor has already sent the max verification texts this hour."""
    now = time.time()
    return len(_recent_sms(_client_ip(request), now)) >= _MAX_SMS_SENDS


def record_sms_send(request: Request) -> None:
    """Count one verification-SMS send against this visitor's hourly cap."""
    now = time.time()
    ip = _client_ip(request)
    _recent_sms(ip, now)
    _sms_sends[ip].append(now)


def minutes_until_unblocked(request: Request) -> int:
    """Roughly how long until the oldest failure ages out (for the message)."""
    dq = _failures.get(_client_ip(request))
    if not dq:
        return 0
    remaining = _WINDOW_SECONDS - (time.time() - dq[0])
    return max(1, int(remaining // 60) + 1)
