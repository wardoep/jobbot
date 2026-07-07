"""
Database connection plumbing.

- ``engine``  : the live connection pool to the database.
- ``Session`` : a factory that hands out short-lived "sessions" (one per request
                or per task). You open one, do your work, commit, and close it.
- ``Base``    : the parent class every table model inherits from.

We support BOTH SQLite (local dev, zero install) and PostgreSQL (production)
through the same code, because SQLAlchemy hides the differences.
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Parent class for all ORM models (see app/models.py)."""


# SQLite needs one extra flag so a single connection can be shared across
# threads (the scheduler in later phases runs in a background thread).
_engine_kwargs = {"future": True}
if settings.using_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **_engine_kwargs)

Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# On SQLite (local dev + the single-server Phase 9 deployment) turn on WAL mode so
# the web app and the scheduler can use the database AT THE SAME TIME without
# "database is locked" errors:
#   - journal_mode=WAL   -> readers never block the writer (and vice-versa)
#   - busy_timeout=5000  -> if both processes try to write at once, wait up to 5s
#                           instead of failing immediately
#   - synchronous=NORMAL -> the safe, fast setting recommended alongside WAL
# busy_timeout/synchronous are per-connection, so this runs on every new connection.
# On PostgreSQL (set DATABASE_URL) none of this runs — Postgres handles concurrency
# itself, so switching databases is genuinely a one-line .env change.
if settings.using_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_concurrency_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
