"""Add completed_by_workout_id to user_quests

Revision ID: b3c7e2f91a45
Revises: da26ee9e5945
Create Date: 2026-02-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3c7e2f91a45'
down_revision = 'da26ee9e5945'
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
