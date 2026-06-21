"""Add wearable heart-rate: per-set timing/HR, session HR summary, samples table

Also merges the four divergent heads that had accumulated
(0206afd2ddfe, 9991b8323957, add_height_inches, b85cd23eba12) so
`alembic upgrade head` resolves to a single head again — same approach as the
earlier merge_three_heads migration.

Adds, for the Apple Watch + WHOOP heart-rate integration:
- sets: start_time, end_time, avg_heart_rate, peak_heart_rate
- workout_sessions: avg_heart_rate, peak_heart_rate, strain, kilojoules,
  hr_zone_seconds (JSON), hr_source
- heart_rate_samples table (raw HR series, attributed to sets by time window)

All new columns are nullable so existing rows and non-wearable workouts are
unaffected.

Revision ID: add_wearable_hr
Revises: 0206afd2ddfe, 9991b8323957, add_height_inches, b85cd23eba12
Create Date: 2026-06-21 00:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_wearable_hr'
down_revision = (
    '0206afd2ddfe',
    '9991b8323957',
    'add_height_inches',
    'b85cd23eba12',
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Per-set timing + HR
    op.add_column('sets', sa.Column('start_time', sa.DateTime(), nullable=True))
    op.add_column('sets', sa.Column('end_time', sa.DateTime(), nullable=True))
    op.add_column('sets', sa.Column('avg_heart_rate', sa.Integer(), nullable=True))
    op.add_column('sets', sa.Column('peak_heart_rate', sa.Integer(), nullable=True))

    # Session-level HR summary
    op.add_column('workout_sessions', sa.Column('avg_heart_rate', sa.Integer(), nullable=True))
    op.add_column('workout_sessions', sa.Column('peak_heart_rate', sa.Integer(), nullable=True))
    op.add_column('workout_sessions', sa.Column('strain', sa.Float(), nullable=True))
    op.add_column('workout_sessions', sa.Column('kilojoules', sa.Float(), nullable=True))
    op.add_column('workout_sessions', sa.Column('hr_zone_seconds', sa.JSON(), nullable=True))
    op.add_column('workout_sessions', sa.Column('hr_source', sa.String(), nullable=True))

    # Raw HR samples
    op.create_table(
        'heart_rate_samples',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('set_id', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('bpm', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['session_id'], ['workout_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['set_id'], ['sets.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_heart_rate_samples_user_id', 'heart_rate_samples', ['user_id'])
    op.create_index('ix_heart_rate_samples_session_id', 'heart_rate_samples', ['session_id'])
    op.create_index('ix_heart_rate_samples_set_id', 'heart_rate_samples', ['set_id'])
    op.create_index('ix_heart_rate_samples_session_ts', 'heart_rate_samples', ['session_id', 'timestamp'])


def downgrade() -> None:
    op.drop_index('ix_heart_rate_samples_session_ts', table_name='heart_rate_samples')
    op.drop_index('ix_heart_rate_samples_set_id', table_name='heart_rate_samples')
    op.drop_index('ix_heart_rate_samples_session_id', table_name='heart_rate_samples')
    op.drop_index('ix_heart_rate_samples_user_id', table_name='heart_rate_samples')
    op.drop_table('heart_rate_samples')

    op.drop_column('workout_sessions', 'hr_source')
    op.drop_column('workout_sessions', 'hr_zone_seconds')
    op.drop_column('workout_sessions', 'kilojoules')
    op.drop_column('workout_sessions', 'strain')
    op.drop_column('workout_sessions', 'peak_heart_rate')
    op.drop_column('workout_sessions', 'avg_heart_rate')

    op.drop_column('sets', 'peak_heart_rate')
    op.drop_column('sets', 'avg_heart_rate')
    op.drop_column('sets', 'end_time')
    op.drop_column('sets', 'start_time')
