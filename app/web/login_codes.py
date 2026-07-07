"""
Short-lived 6-digit codes for passwordless login and optional SMS 2FA.

Pure logic over the ``LoginCode`` table plus ``app/security.py``. The plaintext
code is NEVER stored — we keep only a bcrypt hash and compare against it. Every
code expires after ``CODE_TTL_MINUTES`` and is capped at ``MAX_ATTEMPTS`` guesses;
both limits are enforced here so every caller (the web login flow, the SMS step,
and the ``manage.py login-code`` owner safety-net) gets the same guarantees.

Callers issue a code, send the returned plaintext over email/SMS themselves, and
later verify the digits the user typed. This module never logs or returns the
code anywhere except as the direct return value of ``issue_code``.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as SessionType

from app.models import LoginCode
from app.security import hash_password, verify_password

# How long a freshly issued code stays valid.
CODE_TTL_MINUTES = 10
# Wrong guesses allowed before the code is burned (the Nth+1 guess fails hard).
MAX_ATTEMPTS = 5
# Don't issue/send another code for the same email+purpose within this window.
RESEND_COOLDOWN_SECONDS = 30


def generate_code() -> str:
    """A cryptographically-random 6-digit code, zero-padded ("000000"-"999999").

    Uses ``secrets`` (CSPRNG), never the ``random`` module, so codes are not
    predictable from earlier ones.
    """
    return f"{secrets.randbelow(1_000_000):06d}"


def recently_issued(db: SessionType, email: str, purpose: str) -> bool:
    """True if a code for this (email, purpose) was created within the cooldown.

    Lets the caller throttle resends without revealing anything to the user.
    """
    email = email.strip().lower()
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=RESEND_COOLDOWN_SECONDS)
    return (
        db.query(LoginCode)
        .filter(
            LoginCode.email == email,
            LoginCode.purpose == purpose,
            LoginCode.created_at >= cutoff,
        )
        .first()
        is not None
    )


def issue_code(db: SessionType, email: str, purpose: str) -> str:
    """Invalidate prior unconsumed codes for (email, purpose), then mint a new one.

    Persists only the bcrypt hash; returns the PLAINTEXT code so the caller can
    email/text it. Only the newest code can ever verify.
    """
    email = email.strip().lower()
    now = datetime.now(timezone.utc)

    # Burn any earlier still-usable codes of this purpose so only the newest works.
    prior = (
        db.query(LoginCode)
        .filter(
            LoginCode.email == email,
            LoginCode.purpose == purpose,
            LoginCode.consumed_at.is_(None),
        )
        .all()
    )
    for row in prior:
        row.consumed_at = now

    code = generate_code()
    db.add(
        LoginCode(
            email=email,
            code_hash=hash_password(code),
            purpose=purpose,
            expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
            attempts=0,
        )
    )
    db.commit()
    return code


def verify_code(db: SessionType, email: str, purpose: str, code: str) -> bool:
    """Check ``code`` against the latest unconsumed, unexpired code for (email, purpose).

    Increments the attempt counter on every try. Returns True only on a match (and
    consumes the code). After ``MAX_ATTEMPTS`` wrong guesses the code is consumed
    and all further attempts fail. Expired or missing codes simply fail.
    """
    email = email.strip().lower()
    code = (code or "").strip()
    now = datetime.now(timezone.utc)

    row = (
        db.query(LoginCode)
        .filter(
            LoginCode.email == email,
            LoginCode.purpose == purpose,
            LoginCode.consumed_at.is_(None),
            LoginCode.expires_at > now,
        )
        .order_by(LoginCode.created_at.desc(), LoginCode.id.desc())
        .first()
    )
    if row is None:
        return False

    row.attempts += 1
    # Too many guesses: burn the code and fail (defends against online brute force).
    if row.attempts > MAX_ATTEMPTS:
        row.consumed_at = now
        db.commit()
        return False

    if verify_password(code, row.code_hash):
        row.consumed_at = now
        db.commit()
        return True

    db.commit()
    return False
