"""add user.avatar_filename

Revision ID: b7d2a4c9e1f0
Revises: 96d70bea0c1a
Create Date: 2026-07-01 03:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2a4c9e1f0'
down_revision: Union[str, None] = '96d70bea0c1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Additive, nullable column — existing rows keep NULL (no avatar) and every
    # other table is untouched.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('avatar_filename', sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('avatar_filename')
