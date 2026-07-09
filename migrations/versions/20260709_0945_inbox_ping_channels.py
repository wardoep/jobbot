"""inbox watcher ping channels (telegram/email/ntfy/discord)

Revision ID: c7b2f94e8d13
Revises: a3d8e51c7f42
Create Date: 2026-07-09 09:45:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7b2f94e8d13"
down_revision: Union[str, None] = "a3d8e51c7f42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("inbox_ping_channels", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("ntfy_topic", sa.String(length=300), nullable=True))
        batch.add_column(sa.Column("discord_webhook", sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("discord_webhook")
        batch.drop_column("ntfy_topic")
        batch.drop_column("inbox_ping_channels")
