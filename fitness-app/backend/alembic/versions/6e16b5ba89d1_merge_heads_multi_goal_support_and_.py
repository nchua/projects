"""Merge heads: multi_goal_support and completed_by_workout_id

Revision ID: 6e16b5ba89d1
Revises: add_multi_goal_support, b3c7e2f91a45
Create Date: 2026-02-02 19:38:21.248485

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6e16b5ba89d1'
down_revision = ('add_multi_goal_support', 'b3c7e2f91a45')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
