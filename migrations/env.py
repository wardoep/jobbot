"""
Alembic environment.

This wires Alembic to JobBot's own settings and models so that:
  * the database URL comes from .env (via app.config.settings), and
  * "autogenerate" can compare the live DB against app/models.py.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import the app's settings + models so Alembic knows the URL and the schema.
from app.config import settings
from app.db import Base
import app.models  # noqa: F401  (imported for its side effect: registers tables)

config = context.config

# Inject the real database URL (from .env) into Alembic's config.
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is what "autogenerate" diffs against.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without a live DB connection."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # needed so SQLite can ALTER tables
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # safe ALTERs on SQLite too
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
