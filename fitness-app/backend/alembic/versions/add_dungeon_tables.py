"""Add dungeon tables

Revision ID: add_dungeon_tables
Revises: add_set_id_to_prs
Create Date: 2026-01-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_dungeon_tables'
down_revision = 'add_set_id_to_prs'
branch_labels = None
depends_on = None


def upgrade():
    # Create dungeon_definitions table
    op.create_table('dungeon_definitions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('rank', sa.String(), nullable=False),
        sa.Column('duration_hours', sa.Integer(), nullable=False, server_default='72'),
        sa.Column('base_xp_reward', sa.Integer(), nullable=False),
        sa.Column('bonus_objectives_multiplier', sa.Float(), server_default='1.2'),
        sa.Column('spawn_weight', sa.Integer(), server_default='100'),
        sa.Column('min_user_level', sa.Integer(), server_default='1'),
        sa.Column('max_user_level', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('is_boss_dungeon', sa.Boolean(), server_default='false'),
        sa.Column('is_event_dungeon', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dungeon_definitions_rank'), 'dungeon_definitions', ['rank'], unique=False)

    # Create dungeon_objective_definitions table
    op.create_table('dungeon_objective_definitions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('dungeon_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('objective_type', sa.String(), nullable=False),
        sa.Column('target_value', sa.Integer(), nullable=False),
        sa.Column('target_exercise_id', sa.String(), nullable=True),
        sa.Column('order_index', sa.Integer(), server_default='0'),
        sa.Column('is_required', sa.Boolean(), server_default='true'),
        sa.Column('xp_bonus', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['dungeon_id'], ['dungeon_definitions.id'], ),
        sa.ForeignKeyConstraint(['target_exercise_id'], ['exercises.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dungeon_objective_definitions_dungeon_id'), 'dungeon_objective_definitions', ['dungeon_id'], unique=False)

    # Create user_dungeons table
    op.create_table('user_dungeons',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('dungeon_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='available'),
        sa.Column('spawned_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('claimed_at', sa.DateTime(), nullable=True),
        sa.Column('xp_earned', sa.Integer(), server_default='0'),
        sa.Column('stretch_bonus_xp', sa.Integer(), server_default='0'),
        sa.Column('is_stretch_dungeon', sa.Boolean(), server_default='false'),
        sa.Column('stretch_type', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['dungeon_id'], ['dungeon_definitions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_dungeons_user_id'), 'user_dungeons', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_dungeons_status'), 'user_dungeons', ['status'], unique=False)

    # Create user_dungeon_objectives table
    op.create_table('user_dungeon_objectives',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_dungeon_id', sa.String(), nullable=False),
        sa.Column('objective_definition_id', sa.String(), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_completed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['objective_definition_id'], ['dungeon_objective_definitions.id'], ),
        sa.ForeignKeyConstraint(['user_dungeon_id'], ['user_dungeons.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_dungeon_objectives_user_dungeon_id'), 'user_dungeon_objectives', ['user_dungeon_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_user_dungeon_objectives_user_dungeon_id'), table_name='user_dungeon_objectives')
    op.drop_table('user_dungeon_objectives')
    op.drop_index(op.f('ix_user_dungeons_status'), table_name='user_dungeons')
    op.drop_index(op.f('ix_user_dungeons_user_id'), table_name='user_dungeons')
    op.drop_table('user_dungeons')
    op.drop_index(op.f('ix_dungeon_objective_definitions_dungeon_id'), table_name='dungeon_objective_definitions')
    op.drop_table('dungeon_objective_definitions')
    op.drop_index(op.f('ix_dungeon_definitions_rank'), table_name='dungeon_definitions')
    op.drop_table('dungeon_definitions')
