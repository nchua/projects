"""Add ON DELETE CASCADE to workout_exercises and sets foreign keys.

Previously, deleting an Exercise or a WorkoutSession at the database level
(e.g. GDPR purge, admin cleanup, hard user delete) would fail on
referential-integrity errors because workout_exercises.exercise_id and
sets.workout_exercise_id had no ON DELETE rule.

This migration drops and re-adds those constraints with ondelete='CASCADE'
so that:
  - Deleting a workout_sessions row cascades to its workout_exercises rows
    (and transitively its sets rows).
  - Deleting an exercises row cascades to any workout_exercises rows that
    reference it.
  - Deleting a workout_exercises row cascades to its sets rows.

Revision ID: add_workout_cascade_fks
Revises: add_apple_workout_exercises
Create Date: 2026-04-19
"""
from sqlalchemy import inspect

from alembic import op
from app.core.db_maintenance import purge_workout_orphans

# revision identifiers, used by Alembic.
revision = 'add_workout_cascade_fks'
# Chain off the apple-exercises merge migration, which already collapsed
# f8a2c3d4e5b6 and b2c3d4e5f6g7 into a single head on main.
down_revision = 'add_apple_workout_exercises'
branch_labels = None
depends_on = None


# Canonical names we re-create the constraints under, so downgrade / future
# migrations can reference them without guessing Postgres defaults.
WORKOUT_EXERCISES_SESSION_FK = 'fk_workout_exercises_session_id'
WORKOUT_EXERCISES_EXERCISE_FK = 'fk_workout_exercises_exercise_id'
SETS_WORKOUT_EXERCISE_FK = 'fk_sets_workout_exercise_id'


def _drop_fk_if_exists(bind, table_name: str, column_name: str) -> None:
    """Drop any FK on (table_name.column_name).

    Looks up the actual constraint name via the dialect inspector rather than
    assuming the Postgres default (``{table}_{col}_fkey``). Prod databases may
    have been created with differently-named constraints (e.g. from an older
    ORM version or a manual DBA rename), so hardcoding is unsafe.

    No-ops if no FK is found on that column.
    """
    insp = inspect(bind)
    for fk in insp.get_foreign_keys(table_name):
        if column_name in fk.get('constrained_columns', []):
            op.drop_constraint(fk['name'], table_name, type_='foreignkey')


def upgrade() -> None:
    bind = op.get_bind()
    # SQLite does not support ALTER TABLE ... DROP CONSTRAINT. For tests /
    # local dev against SQLite the FK change is a no-op at the DB level
    # (the Python model now declares ondelete='CASCADE' and SQLAlchemy will
    # emit it when create_all recreates the table).
    if bind.dialect.name == 'sqlite':
        return

    # Pre-clean orphans so CREATE FOREIGN KEY doesn't fail on existing data.
    purge_workout_orphans(bind)

    # workout_exercises.session_id -> workout_sessions.id
    _drop_fk_if_exists(bind, 'workout_exercises', 'session_id')
    op.create_foreign_key(
        WORKOUT_EXERCISES_SESSION_FK,
        'workout_exercises',
        'workout_sessions',
        ['session_id'],
        ['id'],
        ondelete='CASCADE',
    )

    # workout_exercises.exercise_id -> exercises.id
    _drop_fk_if_exists(bind, 'workout_exercises', 'exercise_id')
    op.create_foreign_key(
        WORKOUT_EXERCISES_EXERCISE_FK,
        'workout_exercises',
        'exercises',
        ['exercise_id'],
        ['id'],
        ondelete='CASCADE',
    )

    # sets.workout_exercise_id -> workout_exercises.id
    _drop_fk_if_exists(bind, 'sets', 'workout_exercise_id')
    op.create_foreign_key(
        SETS_WORKOUT_EXERCISE_FK,
        'sets',
        'workout_exercises',
        ['workout_exercise_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        return

    # Restore FKs without cascade behavior. Look up by column so we drop
    # whatever name the upgrade actually created (canonical or legacy).
    _drop_fk_if_exists(bind, 'sets', 'workout_exercise_id')
    op.create_foreign_key(
        SETS_WORKOUT_EXERCISE_FK,
        'sets',
        'workout_exercises',
        ['workout_exercise_id'],
        ['id'],
    )

    _drop_fk_if_exists(bind, 'workout_exercises', 'exercise_id')
    op.create_foreign_key(
        WORKOUT_EXERCISES_EXERCISE_FK,
        'workout_exercises',
        'exercises',
        ['exercise_id'],
        ['id'],
    )

    _drop_fk_if_exists(bind, 'workout_exercises', 'session_id')
    op.create_foreign_key(
        WORKOUT_EXERCISES_SESSION_FK,
        'workout_exercises',
        'workout_sessions',
        ['session_id'],
        ['id'],
    )
