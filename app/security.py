"""
Password helpers.

We NEVER store a user's real password. Instead we store a bcrypt "hash" — a
one-way scramble. To check a login we re-scramble the typed password and compare
the scrambles. bcrypt also salts every hash, so two users with the same password
get different stored values.
"""

from __future__ import annotations

import bcrypt


def hash_password(plain_password: str) -> str:
    """Turn a plain password into a salted bcrypt hash (safe to store)."""
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return True if the plain password matches the stored hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False
