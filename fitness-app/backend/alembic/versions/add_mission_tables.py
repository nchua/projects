"""Add mission system tables (goals, weekly_missions, mission_workouts, exercise_prescriptions)

Revision ID: add_mission_tables
Revises: add_password_reset_tokens
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_mission_tables'
down_revision: Union[str, None] = 'add_password_reset_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create goals table
    op.create_table(
        'goals',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('exercise_id', sa.String(), sa.ForeignKey('exercises.id'), nullable=False),
        sa.Column('target_weight', sa.Float(), nullable=False),
        sa.Column('weight_unit', sa.String(), nullable=False, server_default='lb'),
        sa.Column('deadline', sa.Date(), nullable=False),
        sa.Column('starting_e1rm', sa.Float(), nullable=True),
        sa.Column('current_e1rm', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='active'),
        sa.Column('achieved_at', sa.DateTime(), nullable=True),
        sa.Column('abandoned_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_goals_user_id', 'goals', ['user_id'])
    op.create_index('ix_goals_status', 'goals', ['status'])

    # Create weekly_missions table
    op.create_table(
        'weekly_missions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('goal_id', sa.String(), sa.ForeignKey('goals.id'), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('week_end', sa.Date(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='offered'),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('declined_at', sa.DateTime(), nullable=True),
        sa.Column('xp_reward', sa.Integer(), nullable=False, server_default='200'),
        sa.Column('xp_earned', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('weekly_target', sa.String(), nullable=True),
        sa.Column('coaching_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_weekly_missions_user_id', 'weekly_missions', ['user_id'])
    op.create_index('ix_weekly_missions_goal_id', 'weekly_missions', ['goal_id'])
    op.create_index('ix_weekly_missions_status', 'weekly_missions', ['status'])

    # Create mission_workouts table
    op.create_table(
        'mission_workouts',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('mission_id', sa.String(), sa.ForeignKey('weekly_missions.id'), nullable=False),
        sa.Column('day_number', sa.Integer(), nullable=False),
        sa.Column('focus', sa.String(), nullable=False),
        sa.Column('primary_lift', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('completed_workout_id', sa.String(), sa.ForeignKey('workout_sessions.id'), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('completion_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_mission_workouts_mission_id', 'mission_workouts', ['mission_id'])

    # Create exercise_prescriptions table
    op.create_table(
        'exercise_prescriptions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('mission_workout_id', sa.String(), sa.ForeignKey('mission_workouts.id'), nullable=False),
        sa.Column('exercise_id', sa.String(), sa.ForeignKey('exercises.id'), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False),
        sa.Column('sets', sa.Integer(), nullable=False),
        sa.Column('reps', sa.Integer(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=True),
        sa.Column('weight_unit', sa.String(), nullable=False, server_default='lb'),
        sa.Column('rpe_target', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_completed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('actual_sets', sa.Integer(), nullable=True),
        sa.Column('actual_reps', sa.Integer(), nullable=True),
        sa.Column('actual_weight', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_exercise_prescriptions_mission_workout_id', 'exercise_prescriptions', ['mission_workout_id'])


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_index('ix_exercise_prescriptions_mission_workout_id', table_name='exercise_prescriptions')
    op.drop_table('exercise_prescriptions')

    op.drop_index('ix_mission_workouts_mission_id', table_name='mission_workouts')
    op.drop_table('mission_workouts')

    op.drop_index('ix_weekly_missions_status', table_name='weekly_missions')
    op.drop_index('ix_weekly_missions_goal_id', table_name='weekly_missions')
    op.drop_index('ix_weekly_missions_user_id', table_name='weekly_missions')
    op.drop_table('weekly_missions')

    op.drop_index('ix_goals_status', table_name='goals')
    op.drop_index('ix_goals_user_id', table_name='goals')
    op.drop_table('goals')
