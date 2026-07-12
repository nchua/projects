"""
Tests for the System Directive engine (ARISE v2 spec §5).

Covers the §5.2 rule table (first match wins), generation idempotency on the
(user_id, date) unique key, workout-driven completion for types 2-7, the
next-day rest-directive award, XP routing through award_xp(count_workout=False),
and the /directive endpoints.
"""
import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.directive import DirectiveType, UserDirective
from app.models.exercise import Exercise
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.services import directive_service
from app.services.directive_service import (
    check_directive_completion,
    get_or_generate_directive,
)
from app.services.xp_service import get_or_create_user_progress

# ── Helpers ─────────────────────────────────────────────────────────────────

def _mk_user(create_test_user):
    return create_test_user(email=f"dir-{uuid.uuid4().hex[:8]}@example.com")[0]


def _mk_exercise(db, name="Barbell Bench Press", primary="Chest"):
    exercise = Exercise(
        id=str(uuid.uuid4()),
        name=name,
        category="compound",
        primary_muscle=primary,
        secondary_muscles=[],
        is_custom=False,
        user_id=None,
    )
    db.add(exercise)
    db.commit()
    return exercise


def _mk_workout(db, user_id, exercise, when, sets=((135, 8),)):
    workout = WorkoutSession(user_id=user_id, date=when, duration_minutes=45)
    db.add(workout)
    db.flush()
    we = WorkoutExercise(session_id=workout.id, exercise_id=exercise.id, order_index=0)
    db.add(we)
    db.flush()
    for n, (weight, reps) in enumerate(sets, start=1):
        db.add(Set(workout_exercise_id=we.id, weight=weight, reps=reps,
                   set_number=n, e1rm=weight * (1 + reps / 30)))
    db.commit()
    return workout


def _mk_directive(db, user_id, day, dtype, params=None, completed=False):
    directive = UserDirective(
        user_id=user_id,
        date=day,
        directive_type=dtype.value,
        message="test directive",
        params=params or {},
        is_completed=completed,
    )
    db.add(directive)
    db.commit()
    return directive


def _patch_condition(monkeypatch, score):
    """Pin the Condition score so rule-table tests are deterministic."""
    from app.services.condition_service import band_for_score

    def _fake(db, user_id, client_date=None, user_age=None):
        return {"score": score, "band": band_for_score(score),
                "generated_at": "", "inputs": [], "muscles_cooling": []}

    monkeypatch.setattr(directive_service, "compute_condition", _fake)


# ── Rule table (§5.2, first match wins) ─────────────────────────────────────

def test_rule1_critical_condition_decrees_rest(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    _patch_condition(monkeypatch, 20)

    directive = get_or_generate_directive(db, user.id, date.today())
    assert directive.directive_type == DirectiveType.REST.value
    assert "Rest decreed. Condition 20." in directive.message
    assert directive.params["condition_score"] == 20
    assert directive.xp_reward == 40


def test_rule2_streak_save(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    _patch_condition(monkeypatch, 80)
    today = date.today()

    progress = get_or_create_user_progress(db, user.id)
    progress.current_streak = 5
    progress.last_workout_date = today - timedelta(days=1)
    db.commit()

    directive = get_or_generate_directive(db, user.id, today)
    assert directive.directive_type == DirectiveType.STREAK_SAVE.value
    assert directive.params["streak"] == 5


def test_rule2_skipped_below_battle_ready(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    _patch_condition(monkeypatch, 50)  # STRAINED: no streak-save push
    today = date.today()

    progress = get_or_create_user_progress(db, user.id)
    progress.current_streak = 5
    progress.last_workout_date = today - timedelta(days=1)
    db.commit()

    directive = get_or_generate_directive(db, user.id, today)
    assert directive.directive_type != DirectiveType.STREAK_SAVE.value


def test_rule5_frequency_for_idle_user(db, create_test_user, monkeypatch):
    """A user with no recent workouts gets the VOLUME_LOW insight → frequency."""
    user = _mk_user(create_test_user)
    _patch_condition(monkeypatch, 80)

    directive = get_or_generate_directive(db, user.id, date.today())
    assert directive.directive_type == DirectiveType.FREQUENCY.value
    assert "idleness" in directive.message


def test_rule7_maintain_default(db, create_test_user, monkeypatch):
    """Frequent recent training with no other trigger falls through to maintain."""
    user = _mk_user(create_test_user)
    _patch_condition(monkeypatch, 80)
    exercise = _mk_exercise(db)
    today = date.today()

    # 9 workouts over 4 weeks (>2/wk) with varied loads → no VOLUME_LOW,
    # no PLATEAU (needs >8 sessions on one lift with flat e1RM — loads vary).
    for i in range(9):
        when = datetime.combine(today - timedelta(days=1 + i * 3), datetime.min.time()) + timedelta(hours=10)
        _mk_workout(db, user.id, exercise, when, sets=((135 + i * 10, 5),))

    directive = get_or_generate_directive(db, user.id, today)
    assert directive.directive_type == DirectiveType.MAINTAIN.value
    assert "hunts this week" in directive.message


def test_generation_is_deterministic_per_day(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    _patch_condition(monkeypatch, 80)
    today = date.today()

    first = get_or_generate_directive(db, user.id, today)
    second = get_or_generate_directive(db, user.id, today)
    assert first.id == second.id
    assert db.query(UserDirective).filter(UserDirective.user_id == user.id).count() == 1


# ── Completion: workout-driven types (§5.3) ─────────────────────────────────

def test_workout_completes_maintain_and_awards_xp_once(db, create_test_user):
    user = _mk_user(create_test_user)
    today = date.today()
    _mk_directive(db, user.id, today, DirectiveType.MAINTAIN)

    progress = get_or_create_user_progress(db, user.id)
    xp_before = progress.total_xp
    workouts_before = progress.total_workouts

    result = check_directive_completion(db, user.id, today)
    assert result is not None
    db.commit()

    directive = db.query(UserDirective).filter(UserDirective.user_id == user.id).first()
    assert directive.is_completed is True
    assert directive.completed_at is not None
    assert progress.total_xp == xp_before + 40
    # count_workout=False: the directive award must not inflate workout count
    assert progress.total_workouts == workouts_before

    # Idempotent: second check never double-awards
    assert check_directive_completion(db, user.id, today) is None
    assert progress.total_xp == xp_before + 40


def test_workout_never_completes_rest_directive(db, create_test_user):
    user = _mk_user(create_test_user)
    today = date.today()
    _mk_directive(db, user.id, today, DirectiveType.REST)

    assert check_directive_completion(db, user.id, today) is None
    directive = db.query(UserDirective).filter(UserDirective.user_id == user.id).first()
    assert directive.is_completed is False


def test_reclaim_volume_requires_target_sets(db, create_test_user):
    user = _mk_user(create_test_user)
    exercise = _mk_exercise(db)
    today = date.today()
    _mk_directive(
        db, user.id, today, DirectiveType.RECLAIM_VOLUME,
        params={"exercise_id": exercise.id, "target_sets": 3, "lift": exercise.name},
    )
    when = datetime.combine(today, datetime.min.time()) + timedelta(hours=10)

    # 2 of 3 sets → not complete
    _mk_workout(db, user.id, exercise, when, sets=((135, 8), (135, 8)))
    assert check_directive_completion(db, user.id, today) is None

    # Third set later the same day → complete
    _mk_workout(db, user.id, exercise, when + timedelta(hours=2), sets=((135, 8),))
    assert check_directive_completion(db, user.id, today) is not None


def test_break_plateau_requires_fresh_rep_bucket(db, create_test_user):
    user = _mk_user(create_test_user)
    exercise = _mk_exercise(db)
    today = date.today()

    # 2 weeks of history at 185x5
    for days_ago in (7, 14):
        when = datetime.combine(today - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=10)
        _mk_workout(db, user.id, exercise, when, sets=((185, 5),))

    _mk_directive(
        db, user.id, today, DirectiveType.BREAK_PLATEAU,
        params={"exercise_id": exercise.id, "lift": exercise.name},
    )
    when = datetime.combine(today, datetime.min.time()) + timedelta(hours=10)

    # Same bucket (185x5) → no completion
    _mk_workout(db, user.id, exercise, when, sets=((185, 5),))
    assert check_directive_completion(db, user.id, today) is None

    # New weight bucket (190x5) → pattern broken
    _mk_workout(db, user.id, exercise, when + timedelta(hours=2), sets=((190, 5),))
    assert check_directive_completion(db, user.id, today) is not None


# ── Completion: rest directive on next-day generation ───────────────────────

def test_rest_directive_awarded_next_day_when_rested(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    _patch_condition(monkeypatch, 80)
    today = date.today()
    _mk_directive(db, user.id, today - timedelta(days=1), DirectiveType.REST)

    progress = get_or_create_user_progress(db, user.id)
    xp_before = progress.total_xp

    get_or_generate_directive(db, user.id, today)

    yesterday_row = db.query(UserDirective).filter(
        UserDirective.user_id == user.id,
        UserDirective.date == today - timedelta(days=1),
    ).first()
    assert yesterday_row.is_completed is True
    assert progress.total_xp == xp_before + 40


def test_rest_directive_failed_when_workout_logged(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    _patch_condition(monkeypatch, 80)
    exercise = _mk_exercise(db)
    today = date.today()
    yesterday = today - timedelta(days=1)
    _mk_directive(db, user.id, yesterday, DirectiveType.REST)
    when = datetime.combine(yesterday, datetime.min.time()) + timedelta(hours=10)
    _mk_workout(db, user.id, exercise, when)

    progress = get_or_create_user_progress(db, user.id)
    xp_before = progress.total_xp

    get_or_generate_directive(db, user.id, today)

    yesterday_row = db.query(UserDirective).filter(
        UserDirective.user_id == user.id,
        UserDirective.date == yesterday,
    ).first()
    assert yesterday_row.is_completed is False
    assert progress.total_xp == xp_before


# ── Endpoints ───────────────────────────────────────────────────────────────

def test_get_directive_today_endpoint(client, db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("dir"))
    today = date.today()

    resp = client.get(f"/directive/today?client_date={today.isoformat()}", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data) == {
        "id", "date", "directive_type", "message", "params",
        "xp_reward", "is_completed", "completed_at",
    }
    assert data["date"] == today.isoformat()
    assert data["xp_reward"] == 40
    assert data["is_completed"] is False
    assert data["completed_at"] is None

    # Second call returns the same persisted row (deterministic for the day)
    resp2 = client.get(f"/directive/today?client_date={today.isoformat()}", headers=headers)
    assert resp2.json()["id"] == data["id"]


def test_directive_completes_via_workout_endpoint(client, db, auth_headers, unique_email):
    """End-to-end: POST /workouts triggers the completion hook."""
    headers, user = auth_headers(email=unique_email("dir"))
    exercise = _mk_exercise(db)
    today = date.today()

    first = client.get(f"/directive/today?client_date={today.isoformat()}", headers=headers)
    assert first.json()["is_completed"] is False

    payload = {
        "date": today.isoformat(),
        "duration_minutes": 45,
        "exercises": [{
            "exercise_id": exercise.id,
            "order_index": 0,
            "sets": [{"weight": 135, "weight_unit": "lb", "reps": 8, "set_number": 1}],
        }],
    }
    resp = client.post("/workouts", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text

    after = client.get(f"/directive/today?client_date={today.isoformat()}", headers=headers)
    assert after.json()["is_completed"] is True
    assert after.json()["completed_at"] is not None


def test_directive_history_endpoint(client, db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("dir"))
    today = date.today()
    for offset in range(3):
        _mk_directive(db, user.id, today - timedelta(days=offset), DirectiveType.MAINTAIN)

    resp = client.get("/directive/history?limit=2", headers=headers)
    assert resp.status_code == 200
    directives = resp.json()["directives"]
    assert len(directives) == 2
    # Newest first
    assert directives[0]["date"] == today.isoformat()
    assert directives[1]["date"] == (today - timedelta(days=1)).isoformat()


def test_directive_requires_auth(client):
    assert client.get("/directive/today").status_code in (401, 403)
    assert client.get("/directive/history").status_code in (401, 403)


# ── Unique constraint ───────────────────────────────────────────────────────

def test_unique_user_date_constraint(db, create_test_user):
    user = _mk_user(create_test_user)
    today = date.today()
    _mk_directive(db, user.id, today, DirectiveType.MAINTAIN)

    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        _mk_directive(db, user.id, today, DirectiveType.FREQUENCY)
    db.rollback()
