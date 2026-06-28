"""
Tests for cardio/sport contribution to the muscle cooldown engine.

Set-less Apple-Watch cardio sessions (running, tennis…) previously contributed
zero fatigue because the cooldown engine only accumulated per-set load. These
tests cover the new proxy + time-based path:

- `get_activity_muscles` maps an activity to tracked muscle groups.
- A set-less cardio session now produces cooldown entries for its proxy muscles.
- Longer duration and higher HR intensity both lengthen the cooldown.
- Activities with no proxy (e.g. Yoga) still contribute nothing.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.models.exercise import Exercise
from app.models.workout import WorkoutExercise, WorkoutSession
from app.services.activity_muscles import get_activity_muscles
from app.services.cooldown_service import calculate_cooldowns

# ── Proxy unit tests ────────────────────────────────────────────────────────

def test_running_maps_to_legs_including_calves():
    primary, secondary = get_activity_muscles("Running")
    assert "Quads" in primary
    assert "Hamstrings" in primary
    assert "Calves" in primary          # the signature running muscle
    assert "Glutes" in secondary


def test_tennis_includes_upper_body():
    primary, secondary = get_activity_muscles("Tennis")
    assert "Shoulders" in primary
    assert "Triceps" in secondary


def test_substring_match_handles_prefixed_names():
    assert "Calves" in get_activity_muscles("Trail Running")[0]


def test_unmapped_activity_returns_empty():
    assert get_activity_muscles("Yoga") == ([], [])
    assert get_activity_muscles("") == ([], [])
    # Golf is rotational/forearm-dominant — no defensible tracked-muscle load.
    assert get_activity_muscles("Golf") == ([], [])


# ── DB seeding helpers ──────────────────────────────────────────────────────

def _make_exercise(db, name, primary_muscle, category="Cardio"):
    exercise = Exercise(
        id=str(uuid.uuid4()),
        name=name,
        category=category,
        primary_muscle=primary_muscle,
        secondary_muscles=["Cardio"],
        is_custom=False,
        user_id=None,
    )
    db.add(exercise)
    db.commit()
    return exercise


def _seed_cardio_session(db, user_id, exercise, *, duration_minutes, hr_zone_seconds=None):
    when = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30)
    session = WorkoutSession(
        user_id=user_id,
        date=when,
        duration_minutes=duration_minutes,
        hr_source="apple_watch",
        hr_zone_seconds=hr_zone_seconds,
        notes=f"{exercise.name} - Apple Watch",
    )
    db.add(session)
    db.flush()
    db.add(WorkoutExercise(
        session_id=session.id,
        exercise_id=exercise.id,
        order_index=0,
    ))
    db.commit()
    return session


def _muscle(result, name):
    for m in result["muscles_cooling"]:
        if m["muscle_group"] == name:
            return m
    return None


# ── Engine tests ────────────────────────────────────────────────────────────

def test_cardio_session_produces_cooldown(db, create_test_user):
    user, _ = create_test_user(email="cardio-1@example.com")
    running = _make_exercise(db, "Running", "Legs")
    _seed_cardio_session(db, user.id, running, duration_minutes=60)

    result = calculate_cooldowns(db, user.id)

    quads = _muscle(result, "quads")
    hamstrings = _muscle(result, "hamstrings")
    assert quads is not None, "running should fatigue quads"
    assert hamstrings is not None, "running should fatigue hamstrings"
    assert quads["hours_remaining"] > 0
    # The activity is attributed under the muscle's affected-exercise list.
    assert any(e["exercise_name"] == "Running" for e in quads["affected_exercises"])


def test_longer_cardio_yields_longer_cooldown(db, create_test_user):
    short_user, _ = create_test_user(email="cardio-short@example.com")
    long_user, _ = create_test_user(email="cardio-long@example.com")
    running = _make_exercise(db, "Running", "Legs")

    _seed_cardio_session(db, short_user.id, running, duration_minutes=20)
    _seed_cardio_session(db, long_user.id, running, duration_minutes=120)

    short_quads = _muscle(calculate_cooldowns(db, short_user.id), "quads")
    long_quads = _muscle(calculate_cooldowns(db, long_user.id), "quads")

    assert short_quads is not None and long_quads is not None
    short_hours = short_quads["fatigue_breakdown"]["final_cooldown_hours"]
    long_hours = long_quads["fatigue_breakdown"]["final_cooldown_hours"]
    assert long_hours > short_hours


def test_higher_intensity_yields_longer_cooldown(db, create_test_user):
    easy_user, _ = create_test_user(email="cardio-easy@example.com")
    hard_user, _ = create_test_user(email="cardio-hard@example.com")
    running = _make_exercise(db, "Running", "Legs")

    # Same duration, different zone mix.
    _seed_cardio_session(db, easy_user.id, running, duration_minutes=60,
                         hr_zone_seconds={"z1": 1800, "z2": 1800})
    _seed_cardio_session(db, hard_user.id, running, duration_minutes=60,
                         hr_zone_seconds={"z4": 1800, "z5": 1800})

    easy_quads = _muscle(calculate_cooldowns(db, easy_user.id), "quads")
    hard_quads = _muscle(calculate_cooldowns(db, hard_user.id), "quads")

    assert easy_quads is not None and hard_quads is not None
    easy_hours = easy_quads["fatigue_breakdown"]["final_cooldown_hours"]
    hard_hours = hard_quads["fatigue_breakdown"]["final_cooldown_hours"]
    assert hard_hours > easy_hours


def test_unmapped_cardio_contributes_nothing(db, create_test_user):
    user, _ = create_test_user(email="cardio-yoga@example.com")
    yoga = _make_exercise(db, "Yoga", "Full Body", category="Flexibility")
    _seed_cardio_session(db, user.id, yoga, duration_minutes=60)

    result = calculate_cooldowns(db, user.id)
    assert result["muscles_cooling"] == []


def test_easy_long_cardio_recovers_faster_than_a_strength_day(db, create_test_user):
    # Regression guard for the recovery-realism fix: an easy 2-hour walk must NOT
    # produce a multi-day muscle cooldown rivaling a hard session. Quads from a
    # low-zone 120-min walk should clamp well under two days.
    user, _ = create_test_user(email="cardio-walk@example.com")
    walking = _make_exercise(db, "Walking", "Legs")
    _seed_cardio_session(db, user.id, walking, duration_minutes=120,
                         hr_zone_seconds={"z1": 3600, "z2": 3600})

    quads = _muscle(calculate_cooldowns(db, user.id), "quads")
    assert quads is not None
    assert quads["fatigue_breakdown"]["final_cooldown_hours"] < 48
