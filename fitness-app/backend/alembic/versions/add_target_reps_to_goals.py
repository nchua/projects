"""Add target_reps column to goals table

Revision ID: add_target_reps_to_goals
Revises: add_mission_tables
Create Date: 2026-02-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_target_reps_to_goals'
down_revision: Union[str, None] = 'add_mission_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add target_reps column with default value of 1 (true 1RM goal)
    op.add_column('goals', sa.Column('target_reps', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('goals', 'target_reps')
