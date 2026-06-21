"""Add hk_uuid to workout_sessions for Apple Health workout import (Chunk A)

Adds the HealthKit (Apple Watch) workout UUID column used to dedup imports via
`POST /workouts/import-healthkit`. Cardio imports create a session stamped with
it; strength imports backfill it onto the matched existing session. A partial
unique index on (user_id, hk_uuid) keeps re-imports idempotent — Postgres treats
multiple NULLs as distinct, so non-HealthKit rows are unaffected. Mirrors the
client_id partial-index precedent.

Chained off the WHOOP API head (add_whoop_connections).

Revision ID: add_healthkit_uuid
Revises: add_whoop_connections
Create Date: 2026-06-21 00:45:00.000000

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_healthkit_uuid'
down_revision = 'add_whoop_connections'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'workout_sessions', sa.Column('hk_uuid', sa.String(), nullable=True)
    )
    # Per-user HealthKit UUID uniqueness (partial — multiple NULLs distinct in PG).
    op.create_index(
        'ix_workout_sessions_user_hk_uuid_unique',
        'workout_sessions',
        ['user_id', 'hk_uuid'],
        unique=True,
        postgresql_where=sa.text('hk_uuid IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index(
        'ix_workout_sessions_user_hk_uuid_unique', table_name='workout_sessions'
    )
    op.drop_column('workout_sessions', 'hk_uuid')
