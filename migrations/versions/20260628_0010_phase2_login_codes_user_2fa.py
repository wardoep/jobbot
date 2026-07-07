"""phase 2: login codes + user 2fa fields

Adds the passwordless-login support:
  - new ``login_codes`` table (short-lived, bcrypt-hashed 6-digit codes), and
  - three additive ``users`` columns: display_name, phone, sms_2fa_enabled.

All new ``users`` columns are nullable / defaulted, so existing rows backfill
cleanly (sms_2fa_enabled gets server_default false -> False everywhere).
batch_alter_table is used so this also works on SQLite.

Revision ID: c3e5f7a9d124
Revises: b2d4f6a8c012
Create Date: 2026-06-28 00:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e5f7a9d124'
down_revision: Union[str, None] = 'b2d4f6a8c012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New table for short-lived login / SMS codes (plaintext is never stored).
    op.create_table(
        'login_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('code_hash', sa.String(length=255), nullable=False),
        sa.Column('purpose', sa.String(length=20), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('login_codes', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_login_codes_email'), ['email'], unique=False
        )

    # Additive, backward-compatible columns on users.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('display_name', sa.String(length=120), nullable=True)
        )
        batch_op.add_column(
            sa.Column('phone', sa.String(length=40), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                'sms_2fa_enabled',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('sms_2fa_enabled')
        batch_op.drop_column('phone')
        batch_op.drop_column('display_name')

    with op.batch_alter_table('login_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_login_codes_email'))

    op.drop_table('login_codes')
