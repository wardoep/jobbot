"""inbox watcher: per-user IMAP connect + inbox_events audit table

Revision ID: a3d8e51c7f42
Revises: f1a7c3d9b204
Create Date: 2026-07-09 09:25:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3d8e51c7f42"
down_revision: Union[str, None] = "f1a7c3d9b204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("imap_host", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("imap_email", sa.String(length=320), nullable=True))
        batch.add_column(sa.Column("imap_password", sa.String(length=500), nullable=True))
        batch.add_column(
            sa.Column("inbox_enabled", sa.Boolean(), nullable=False,
                      server_default=sa.false())
        )
        batch.add_column(sa.Column("inbox_last_uid", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("inbox_scanned_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.create_table(
        "inbox_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), index=True,
                  nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("job_id", sa.Integer(),
                  sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("subject", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "message_id", name="uq_inbox_user_message"),
    )


def downgrade() -> None:
    op.drop_table("inbox_events")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("inbox_scanned_at")
        batch.drop_column("inbox_last_uid")
        batch.drop_column("inbox_enabled")
        batch.drop_column("imap_password")
        batch.drop_column("imap_email")
        batch.drop_column("imap_host")
