"""Add workout_sessions.local_date — the user's local calendar day

The `date` column mixes two conventions: manual/screenshot logs store the
local day at midnight, watch imports store a real UTC instant. Day bucketing
(Hunt Log calendar, training-calendar PWA) has repeatedly broken on that
ambiguity, so the local day becomes an explicit column.

Backfill: midnight rows are manual/screenshot logs whose date part IS the
local day. Non-midnight rows are UTC instants whose historical timezone is
unrecoverable — they stay NULL and readers keep the tz-offset fallback.

Revision ID: workout_local_date
Revises: lying_tricep_aliases
Create Date: 2026-08-16

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'workout_local_date'
down_revision = 'lying_tricep_aliases'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('workout_sessions', sa.Column('local_date', sa.Date(), nullable=True))
    op.create_index(
        op.f('ix_workout_sessions_local_date'),
        'workout_sessions',
        ['local_date'],
    )
    op.execute(
        "UPDATE workout_sessions "
        "SET local_date = date::date "
        "WHERE date::time = '00:00:00'"
    )


def downgrade():
    op.drop_index(op.f('ix_workout_sessions_local_date'), table_name='workout_sessions')
    op.drop_column('workout_sessions', 'local_date')
