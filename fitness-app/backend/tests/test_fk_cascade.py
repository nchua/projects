"""
Tests for ON DELETE CASCADE behaviour on workout foreign keys.

With the cascade rules in place:
- Deleting an Exercise cascades to its WorkoutExercise rows.
- Deleting a WorkoutSession cascades to its WorkoutExercise rows, which in
  turn cascades to the Set rows under those exercises.
- Deleting a WorkoutExercise directly cascades to its Set rows.

The test database is SQLite with `PRAGMA foreign_keys=ON` (see conftest),
but because the engine connection may have been established before the
pragma listener was registered (main.py runs migrations on import), each
test re-asserts the pragma before exercising the cascade.
"""
from datetime import datetime, timezone

from sqlalchemy import text

from app.models.exercise import Exercise
from app.models.workout import Set, WeightUnit, WorkoutExercise, WorkoutSession


def _ensure_sqlite_fk(db) -> None:
    """Make sure ON DELETE CASCADE is actually honored on the current connection."""
    db.execute(text("PRAGMA foreign_keys=ON"))


def _make_session_with_sets(db, user_id: str):
    """Create a workout session with one exercise and two sets, return ids."""
    exercise = Exercise(name="Cascade Test Lift", category="compound", is_custom=False)
    db.add(exercise)
    db.flush()

    session = WorkoutSession(
        user_id=user_id,
        date=datetime.now(timezone.utc),
        duration_minutes=45,
    )
    db.add(session)
    db.flush()

    we = WorkoutExercise(
        session_id=session.id,
        exercise_id=exercise.id,
        order_index=0,
    )
    db.add(we)
    db.flush()

    s1 = Set(
        workout_exercise_id=we.id,
        weight=100.0,
        weight_unit=WeightUnit.LB,
        reps=5,
        set_number=1,
    )
    s2 = Set(
        workout_exercise_id=we.id,
        weight=110.0,
        weight_unit=WeightUnit.LB,
        reps=5,
        set_number=2,
    )
    db.add_all([s1, s2])
    db.commit()
    return exercise.id, session.id, we.id, [s1.id, s2.id]


class TestWorkoutCascade:
    def test_delete_exercise_removes_workout_exercises(self, db, create_test_user):
        user, _ = create_test_user()
        _ensure_sqlite_fk(db)
        exercise_id, _session_id, we_id, _set_ids = _make_session_with_sets(db, user.id)

        # Sanity check
        assert db.query(WorkoutExercise).filter_by(id=we_id).first() is not None

        # Delete the exercise row at the SQL layer so the DB-level ON DELETE
        # CASCADE is what's exercised (not the ORM relationship cascade).
        db.execute(text("DELETE FROM exercises WHERE id = :eid"), {"eid": exercise_id})
        db.commit()
        db.expire_all()

        assert db.query(WorkoutExercise).filter_by(id=we_id).first() is None

    def test_delete_session_cascades_through_sets(self, db, create_test_user):
        user, _ = create_test_user()
        _ensure_sqlite_fk(db)
        _exercise_id, session_id, we_id, set_ids = _make_session_with_sets(db, user.id)

        db.execute(text("DELETE FROM workout_sessions WHERE id = :sid"), {"sid": session_id})
        db.commit()
        db.expire_all()

        assert db.query(WorkoutExercise).filter_by(id=we_id).first() is None
        assert db.query(Set).filter(Set.id.in_(set_ids)).count() == 0

    def test_delete_workout_exercise_cascades_to_sets(self, db, create_test_user):
        user, _ = create_test_user()
        _ensure_sqlite_fk(db)
        _exercise_id, _session_id, we_id, set_ids = _make_session_with_sets(db, user.id)

        db.execute(text("DELETE FROM workout_exercises WHERE id = :wid"), {"wid": we_id})
        db.commit()
        db.expire_all()

        assert db.query(Set).filter(Set.id.in_(set_ids)).count() == 0
