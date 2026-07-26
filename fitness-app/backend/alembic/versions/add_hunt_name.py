"""Add name to workout_sessions (custom hunt names)

Revision ID: add_hunt_name
Revises: add_pr_gates
Create Date: 2026-07-20

Nullable so every existing session is unaffected; display falls back to the
derived suggested name and finally the session date.
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_hunt_name'
down_revision = 'add_pr_gates'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'workout_sessions',
        sa.Column('name', sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('workout_sessions', 'name')
