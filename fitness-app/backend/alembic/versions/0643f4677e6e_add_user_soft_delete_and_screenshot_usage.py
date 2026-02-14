"""add_user_soft_delete_and_screenshot_usage

Revision ID: 0643f4677e6e
Revises: e741d5fb553c
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0643f4677e6e'
down_revision: Union[str, None] = '0206afd2ddfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add soft-delete columns to users table
    op.add_column('users', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('deleted_at', sa.DateTime(), nullable=True))

    # Create screenshot_usage table
    op.create_table(
        'screenshot_usage',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('screenshots_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_screenshot_usage_user_id', 'screenshot_usage', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_screenshot_usage_user_id', table_name='screenshot_usage')
    op.drop_table('screenshot_usage')
    op.drop_column('users', 'deleted_at')
    op.drop_column('users', 'is_deleted')
