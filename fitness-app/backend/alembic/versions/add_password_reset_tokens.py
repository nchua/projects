"""Add password_reset_tokens table

Revision ID: add_password_reset_tokens
Revises: b3c7e2f91a45
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_password_reset_tokens'
down_revision: Union[str, None] = 'b3c7e2f91a45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create password_reset_tokens table
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('code', sa.String(6), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('attempts', sa.Integer(), default=0, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Create index for email lookups
    op.create_index('ix_password_reset_tokens_email', 'password_reset_tokens', ['email'])


def downgrade() -> None:
    op.drop_index('ix_password_reset_tokens_email', table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
