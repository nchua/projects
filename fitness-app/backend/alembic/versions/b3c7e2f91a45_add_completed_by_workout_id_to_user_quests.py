"""Add completed_by_workout_id to user_quests

Revision ID: b3c7e2f91a45
Revises: c1a2b3d4e5f6
Create Date: 2026-02-01 12:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'b3c7e2f91a45'
down_revision = 'c1a2b3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column to track which workout completed each quest
    op.add_column('user_quests', sa.Column('completed_by_workout_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_user_quests_completed_by_workout',
        'user_quests',
        'workout_sessions',
        ['completed_by_workout_id'],
        ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_user_quests_completed_by_workout', 'user_quests', type_='foreignkey')
    op.drop_column('user_quests', 'completed_by_workout_id')
