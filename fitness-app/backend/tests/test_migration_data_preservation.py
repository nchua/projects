"""Test the orphan-purge logic used by add_workout_cascade_fks migration.

The Postgres side of the migration runs `_purge_orphans(bind)` before
re-adding the foreign keys with ondelete='CASCADE' — if we didn't,
CREATE FOREIGN KEY would raise ForeignKeyViolation on any pre-existing
orphan row. This test seeds the orphan patterns we've seen in prod,
runs the purge, and asserts only the orphans were deleted.

Runs under the shared conftest (in-memory SQLite) — we import the purge
helper directly so we test the SQL behavior without needing Postgres.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.core.db_maintenance import purge_workout_orphans


def _iso_now():
    return datetime.now(timezone.utc)


def _fk_off(db):
    """Defer SQLite FK enforcement to COMMIT for the current transaction.

    The migration-under-test is designed to run against a DB where orphan
    rows already exist (that's why purge is needed), so we replicate that
    precondition here. Under real Postgres migrations the FKs are dropped
    before the purge runs.

    PRAGMA foreign_keys is a no-op inside a transaction on SQLite, but
    PRAGMA defer_foreign_keys defers enforcement until COMMIT — and since
    the purge will delete the offenders before we ever commit, the
    constraint check at COMMIT passes.
    """
    db.execute(text("PRAGMA defer_foreign_keys=ON"))


def test_purge_removes_orphan_sets_but_keeps_valid_ones(db):
    """Orphan set rows (parent workout_exercise deleted out from under them)
    must be cleaned up; valid sets must not be touched.
    """
    _fk_off(db)

    # Seed: an exercise, a session, a valid workout_exercise with a set,
    # and an orphan set pointing at a nonexistent workout_exercise_id.
    exercise_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    we_id = str(uuid.uuid4())
    valid_set_id = str(uuid.uuid4())
    orphan_set_id = str(uuid.uuid4())
    bogus_we_id = str(uuid.uuid4())

    now = _iso_now().isoformat()

    db.execute(text("""
        INSERT INTO exercises (id, name, canonical_id, is_custom, created_at, updated_at)
        VALUES (:id, 'Test Squat', :id, false, :now, :now)
    """), {"id": exercise_id, "now": now})
    db.execute(text("""
        INSERT INTO users (id, email, password_hash, is_deleted, created_at, updated_at)
        VALUES (:id, 'orphan-test@example.com', 'x', false, :now, :now)
    """), {"id": user_id, "now": now})
    db.execute(text("""
        INSERT INTO workout_sessions (id, user_id, date, created_at, updated_at)
        VALUES (:id, :uid, :now, :now, :now)
    """), {"id": session_id, "uid": user_id, "now": now})
    db.execute(text("""
        INSERT INTO workout_exercises (id, session_id, exercise_id, order_index, created_at)
        VALUES (:id, :sid, :eid, 0, :now)
    """), {"id": we_id, "sid": session_id, "eid": exercise_id, "now": now})
    db.execute(text("""
        INSERT INTO sets (id, workout_exercise_id, weight, weight_unit, reps, set_number, created_at)
        VALUES (:id, :we_id, 100, 'lb', 5, 1, :now)
    """), {"id": valid_set_id, "we_id": we_id, "now": now})
    db.execute(text("""
        INSERT INTO sets (id, workout_exercise_id, weight, weight_unit, reps, set_number, created_at)
        VALUES (:id, :we_id, 100, 'lb', 5, 1, :now)
    """), {"id": orphan_set_id, "we_id": bogus_we_id, "now": now})
    db.commit()

    purge_workout_orphans(db.get_bind())
    db.commit()

    remaining = {
        row[0]
        for row in db.execute(text("SELECT id FROM sets")).fetchall()
    }
    assert valid_set_id in remaining, "Valid set was incorrectly deleted"
    assert orphan_set_id not in remaining, "Orphan set was not cleaned up"


def test_purge_removes_orphan_workout_exercises(db):
    """A workout_exercise whose parent session OR exercise is missing must be
    cleaned up; valid rows must be preserved.
    """
    _fk_off(db)

    user_id = str(uuid.uuid4())
    exercise_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    valid_we_id = str(uuid.uuid4())
    orphan_session_we_id = str(uuid.uuid4())
    orphan_exercise_we_id = str(uuid.uuid4())
    now = _iso_now().isoformat()

    db.execute(text("""
        INSERT INTO users (id, email, password_hash, is_deleted, created_at, updated_at)
        VALUES (:id, 'orphan-we@example.com', 'x', false, :now, :now)
    """), {"id": user_id, "now": now})
    db.execute(text("""
        INSERT INTO exercises (id, name, canonical_id, is_custom, created_at, updated_at)
        VALUES (:id, 'Test Bench', :id, false, :now, :now)
    """), {"id": exercise_id, "now": now})
    db.execute(text("""
        INSERT INTO workout_sessions (id, user_id, date, created_at, updated_at)
        VALUES (:id, :uid, :now, :now, :now)
    """), {"id": session_id, "uid": user_id, "now": now})

    # Valid workout_exercise.
    db.execute(text("""
        INSERT INTO workout_exercises (id, session_id, exercise_id, order_index, created_at)
        VALUES (:id, :sid, :eid, 0, :now)
    """), {"id": valid_we_id, "sid": session_id, "eid": exercise_id, "now": now})
    # Orphan — nonexistent session.
    db.execute(text("""
        INSERT INTO workout_exercises (id, session_id, exercise_id, order_index, created_at)
        VALUES (:id, :sid, :eid, 0, :now)
    """), {"id": orphan_session_we_id, "sid": str(uuid.uuid4()), "eid": exercise_id, "now": now})
    # Orphan — nonexistent exercise.
    db.execute(text("""
        INSERT INTO workout_exercises (id, session_id, exercise_id, order_index, created_at)
        VALUES (:id, :sid, :eid, 0, :now)
    """), {"id": orphan_exercise_we_id, "sid": session_id, "eid": str(uuid.uuid4()), "now": now})
    db.commit()

    purge_workout_orphans(db.get_bind())
    db.commit()

    remaining = {
        row[0]
        for row in db.execute(text("SELECT id FROM workout_exercises")).fetchall()
    }
    assert valid_we_id in remaining
    assert orphan_session_we_id not in remaining
    assert orphan_exercise_we_id not in remaining
