"""
Tests for the workout-list summary surfacing Apple-Watch cardio as an activity.

A set-less Apple-Watch cardio session must round-trip through ``GET /workouts``
as an activity: ``is_activity`` true, an ``activity_type`` parsed from notes,
calories converted from kilojoules, an ``exertion_score`` from the HR zones, and
proxy muscles (Quads/Hamstrings) rather than the coarse seeded "Legs".
"""
import uuid
from datetime import datetime, timezone

from app.core.exertion import compute_exertion_score
from app.models.exercise import Exercise
from app.models.workout import WorkoutExercise, WorkoutSession


def _running_exercise(db):
    exercise = Exercise(
        id=str(uuid.uuid4()),
        name="Running",
        category="Cardio",
        primary_muscle="Legs",
        secondary_muscles=["Cardio"],
        is_custom=False,
        user_id=None,
    )
    db.add(exercise)
    db.flush()
    return exercise


def test_apple_watch_cardio_renders_as_activity(client, auth_headers, db):
    headers, user = auth_headers(email="aw-cardio@example.com")
    running = _running_exercise(db)

    zones = {"z2": 1200, "z3": 900}
    session = WorkoutSession(
        user_id=user.id,
        date=datetime.now(timezone.utc).replace(tzinfo=None),
        duration_minutes=45,
        hr_source="apple_watch",
        kilojoules=1500.0,
        hr_zone_seconds=zones,
        notes="Running - Apple Watch | Distance: 8000m",
    )
    db.add(session)
    db.flush()
    db.add(WorkoutExercise(session_id=session.id, exercise_id=running.id, order_index=0))
    db.commit()

    resp = client.get("/workouts", headers=headers)
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["id"] == session.id)

    assert row["is_activity"] is True
    assert row["is_whoop_activity"] is False
    assert row["activity_type"] == "Running"
    assert row["calories"] == round(1500.0 * 0.239006)
    assert row["exertion_score"] == compute_exertion_score(zones)
    assert row["strain"] is None  # Apple Watch carries no strain
    assert row["hr_source"] == "apple_watch"
    # Proxy muscles replace the coarse seeded "Legs".
    assert "Quads" in row["primary_muscles"]
    assert "Hamstrings" in row["primary_muscles"]
    assert "Legs" not in row["primary_muscles"]


def test_apple_watch_session_without_activity_notes_is_not_activity(client, auth_headers, db):
    # hr_source is apple_watch and there are no sets, but the notes don't encode
    # an activity type -> not surfaced as an activity (guarded on activity_type).
    headers, user = auth_headers(email="aw-noactivity@example.com")
    running = _running_exercise(db)

    session = WorkoutSession(
        user_id=user.id,
        date=datetime.now(timezone.utc).replace(tzinfo=None),
        duration_minutes=30,
        hr_source="apple_watch",
        notes="just a freeform note",
    )
    db.add(session)
    db.flush()
    db.add(WorkoutExercise(session_id=session.id, exercise_id=running.id, order_index=0))
    db.commit()

    resp = client.get("/workouts", headers=headers)
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["id"] == session.id)

    assert row["is_activity"] is False
    assert row["activity_type"] is None
