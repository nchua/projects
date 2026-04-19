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
Revises: f8a2c3d4e5b6, b2c3d4e5f6g7
Create Date: 2026-04-19
"""
from alembic import op

from app.core.db_maintenance import purge_workout_orphans

# revision identifiers, used by Alembic.
revision = 'add_workout_cascade_fks'
# Merges the two open heads so this can apply as a single head going forward.
down_revision = ('f8a2c3d4e5b6', 'b2c3d4e5f6g7')
branch_labels = None
depends_on = None


# Postgres default constraint names (table_col_fkey).
WORKOUT_EXERCISES_SESSION_FK = 'workout_exercises_session_id_fkey'
WORKOUT_EXERCISES_EXERCISE_FK = 'workout_exercises_exercise_id_fkey'
SETS_WORKOUT_EXERCISE_FK = 'sets_workout_exercise_id_fkey'


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
    op.drop_constraint(
        WORKOUT_EXERCISES_SESSION_FK, 'workout_exercises', type_='foreignkey'
    )
    op.create_foreign_key(
        WORKOUT_EXERCISES_SESSION_FK,
        'workout_exercises',
        'workout_sessions',
        ['session_id'],
        ['id'],
        ondelete='CASCADE',
    )

    # workout_exercises.exercise_id -> exercises.id
    op.drop_constraint(
        WORKOUT_EXERCISES_EXERCISE_FK, 'workout_exercises', type_='foreignkey'
    )
    op.create_foreign_key(
        WORKOUT_EXERCISES_EXERCISE_FK,
        'workout_exercises',
        'exercises',
        ['exercise_id'],
        ['id'],
        ondelete='CASCADE',
    )

    # sets.workout_exercise_id -> workout_exercises.id
    op.drop_constraint(
        SETS_WORKOUT_EXERCISE_FK, 'sets', type_='foreignkey'
    )
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

    # Restore FKs without cascade behavior (original state).
    op.drop_constraint(
        SETS_WORKOUT_EXERCISE_FK, 'sets', type_='foreignkey'
    )
    op.create_foreign_key(
        SETS_WORKOUT_EXERCISE_FK,
        'sets',
        'workout_exercises',
        ['workout_exercise_id'],
        ['id'],
    )

    op.drop_constraint(
        WORKOUT_EXERCISES_EXERCISE_FK, 'workout_exercises', type_='foreignkey'
    )
    op.create_foreign_key(
        WORKOUT_EXERCISES_EXERCISE_FK,
        'workout_exercises',
        'exercises',
        ['exercise_id'],
        ['id'],
    )

    op.drop_constraint(
        WORKOUT_EXERCISES_SESSION_FK, 'workout_exercises', type_='foreignkey'
    )
    op.create_foreign_key(
        WORKOUT_EXERCISES_SESSION_FK,
        'workout_exercises',
        'workout_sessions',
        ['session_id'],
        ['id'],
    )
