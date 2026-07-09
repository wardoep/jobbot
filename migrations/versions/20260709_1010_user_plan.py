"""user plan tier (free/premium) + optional expiry

Revision ID: d9e4a17b3c58
Revises: c7b2f94e8d13
Create Date: 2026-07-09 10:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9e4a17b3c58"
down_revision: Union[str, None] = "c7b2f94e8d13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("plan", sa.String(length=20), nullable=False,
                      server_default="free")
        )
        batch.add_column(
            sa.Column("premium_until", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("premium_until")
        batch.drop_column("plan")
