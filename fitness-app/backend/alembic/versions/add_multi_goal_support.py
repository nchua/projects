"""Add multi-goal support: mission_goals junction table and training_split to weekly_missions

Revision ID: add_multi_goal_support
Revises: add_target_reps_to_goals
Create Date: 2026-02-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_multi_goal_support'
down_revision: Union[str, None] = 'add_target_reps_to_goals'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add training_split column to weekly_missions
    op.add_column('weekly_missions', sa.Column('training_split', sa.String(), nullable=True))

    # Make goal_id nullable (for new multi-goal missions that use junction table)
    op.alter_column('weekly_missions', 'goal_id',
                    existing_type=sa.String(),
                    nullable=True)

    # Create mission_goals junction table
    op.create_table(
        'mission_goals',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('mission_id', sa.String(), sa.ForeignKey('weekly_missions.id'), nullable=False),
        sa.Column('goal_id', sa.String(), sa.ForeignKey('goals.id'), nullable=False),
        sa.Column('workouts_completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_satisfied', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_mission_goals_mission_id', 'mission_goals', ['mission_id'])
    op.create_index('ix_mission_goals_goal_id', 'mission_goals', ['goal_id'])

    # Migrate existing missions to use junction table
    # For each existing mission with goal_id, create a corresponding mission_goal entry
    conn = op.get_bind()
    missions = conn.execute(
        sa.text("SELECT id, goal_id FROM weekly_missions WHERE goal_id IS NOT NULL")
    ).fetchall()

    for mission_id, goal_id in missions:
        import uuid
        from datetime import datetime
        conn.execute(
            sa.text("""
                INSERT INTO mission_goals (id, mission_id, goal_id, workouts_completed, is_satisfied, created_at)
                VALUES (:id, :mission_id, :goal_id, 0, false, :created_at)
            """),
            {
                "id": str(uuid.uuid4()),
                "mission_id": mission_id,
                "goal_id": goal_id,
                "created_at": datetime.utcnow()
            }
        )


def downgrade() -> None:
    # Drop mission_goals table
    op.drop_index('ix_mission_goals_goal_id', table_name='mission_goals')
    op.drop_index('ix_mission_goals_mission_id', table_name='mission_goals')
    op.drop_table('mission_goals')

    # Make goal_id non-nullable again
    op.alter_column('weekly_missions', 'goal_id',
                    existing_type=sa.String(),
                    nullable=False)

    # Remove training_split column
    op.drop_column('weekly_missions', 'training_split')
