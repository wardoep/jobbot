"""add alert preference fields (slack webhook + last digest time)

Revision ID: b2d4f6a8c012
Revises: 05465929e528
Create Date: 2026-06-19 06:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2d4f6a8c012'
down_revision: Union[str, None] = '05465929e528'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Two new optional columns on `preferences` for Phase 5 alerts:
    #   - slack_webhook: a user's personal Slack Incoming Webhook URL.
    #   - last_digest_at: when we last sent them a digest (rate-limits digests).
    # batch_alter_table is required so this also works on SQLite.
    with op.batch_alter_table('preferences', schema=None) as batch_op:
        batch_op.add_column(sa.Column('slack_webhook', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('last_digest_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('preferences', schema=None) as batch_op:
        batch_op.drop_column('last_digest_at')
        batch_op.drop_column('slack_webhook')
