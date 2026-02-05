"""add_goal_progress_snapshot_table

Revision ID: 0206afd2ddfe
Revises: 6e16b5ba89d1
Create Date: 2026-02-04 18:08:45.917325

After applying this migration, run the backfill script to populate
initial snapshots from PR history:

    python scripts/backfill_goal_progress.py

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0206afd2ddfe'
down_revision = '6e16b5ba89d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('goal_progress_snapshots',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('goal_id', sa.String(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('e1rm', sa.Float(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=True),
        sa.Column('reps', sa.Integer(), nullable=True),
        sa.Column('workout_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['goal_id'], ['goals.id']),
        sa.ForeignKeyConstraint(['workout_id'], ['workout_sessions.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_goal_progress_snapshots_goal_id', 'goal_progress_snapshots', ['goal_id'], unique=False)
    op.create_index('ix_goal_progress_snapshots_recorded_at', 'goal_progress_snapshots', ['recorded_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_goal_progress_snapshots_recorded_at', table_name='goal_progress_snapshots')
    op.drop_index('ix_goal_progress_snapshots_goal_id', table_name='goal_progress_snapshots')
    op.drop_table('goal_progress_snapshots')
