"""Add username to users

Revision ID: add_username_to_users
Revises: add_height_inches
Create Date: 2026-01-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_username_to_users'
down_revision: Union[str, None] = 'add_height_inches'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add username column to users table
    op.add_column('users', sa.Column('username', sa.String(20), nullable=True))

    # Create unique index for username
    op.create_index('ix_users_username', 'users', ['username'], unique=True)


def downgrade() -> None:
    # Remove index and column
    op.drop_index('ix_users_username', table_name='users')
    op.drop_column('users', 'username')
