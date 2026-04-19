"""Add client_id idempotency column to workout_sessions.

The iOS offline queue stamps a UUID on every WorkoutCreate. When a retry
arrives after a network blip that actually succeeded server-side, the
backend now looks up the existing row by (user_id, client_id) and returns
it instead of creating a duplicate. The partial unique index enforces
this at the DB level — NULLs (legacy rows / web clients) are ignored by
Postgres' multi-NULL uniqueness rules.

Also merges the two pre-existing alembic heads so `upgrade head` stays
single-targeted after this lands.

Revision ID: add_workout_client_id
Revises: f8a2c3d4e5b6, b2c3d4e5f6g7
Create Date: 2026-04-19
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_workout_client_id'
down_revision = ('f8a2c3d4e5b6', 'b2c3d4e5f6g7')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'workout_sessions',
        sa.Column('client_id', sa.String(), nullable=True),
    )
    op.create_index(
        'ix_workout_sessions_client_id',
        'workout_sessions',
        ['client_id'],
    )

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # Partial unique index — Postgres permits multiple NULLs under a
        # unique constraint, so legacy rows and web clients (no client_id)
        # aren't affected.
        op.create_index(
            'ix_workout_sessions_user_client_unique',
            'workout_sessions',
            ['user_id', 'client_id'],
            unique=True,
            postgresql_where=sa.text('client_id IS NOT NULL'),
        )
    else:
        # SQLite doesn't support partial indexes via Alembic's
        # `postgresql_where`, and dev/test traffic is too low to hit the
        # race. Skip the uniqueness constraint on SQLite; the application-
        # layer check in _create_workout_impl is sufficient there.
        pass


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.drop_index(
            'ix_workout_sessions_user_client_unique',
            table_name='workout_sessions',
        )
    op.drop_index(
        'ix_workout_sessions_client_id',
        table_name='workout_sessions',
    )
    op.drop_column('workout_sessions', 'client_id')
