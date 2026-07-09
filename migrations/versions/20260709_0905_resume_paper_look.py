"""resume paper_json + look (builder look preview & persistence)

Revision ID: f1a7c3d9b204
Revises: e9e034cb5133
Create Date: 2026-07-09 09:05:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a7c3d9b204"
down_revision: Union[str, None] = "e9e034cb5133"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("resumes") as batch:
        batch.add_column(sa.Column("paper_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("look", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("resumes") as batch:
        batch.drop_column("look")
        batch.drop_column("paper_json")
