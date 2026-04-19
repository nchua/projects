"""Database maintenance helpers shared between Alembic migrations and tests.

Keeping orphan-cleanup SQL in one place prevents drift between the migration
logic (run at deploy time) and the tests that prove the logic is correct.
"""
from sqlalchemy import text


def purge_workout_orphans(bind) -> None:
    """Delete rows that would fail the workout CASCADE foreign-key migration.

    Run in dependency order: sets first (their parent is workout_exercises),
    then workout_exercises (parents are workout_sessions + exercises). Old
    non-cascading FKs left orphan rows behind in prod via soft-delete races
    and since-removed debug endpoints.
    """
    bind.execute(text("""
        DELETE FROM sets
        WHERE workout_exercise_id IS NOT NULL
          AND workout_exercise_id NOT IN (SELECT id FROM workout_exercises)
    """))
    bind.execute(text("""
        DELETE FROM workout_exercises
        WHERE (session_id IS NOT NULL
               AND session_id NOT IN (SELECT id FROM workout_sessions))
           OR (exercise_id IS NOT NULL
               AND exercise_id NOT IN (SELECT id FROM exercises))
    """))
