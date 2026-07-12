"""
Tests for the PR Gate engine (ARISE v2 spec §6) and its trend prerequisite.

Covers weekly_slope/projected_e1rm math (§6.1), the spawn rules (§6.2:
projection beats baseline, Condition gate, scarcity caps, data prerequisite),
ranking with the big-three bump (§6.3), lifecycle transitions (§6.4:
clear awards XP with no claim step, expiry is quiet), and the /gates
endpoints (§6.5).
"""
import uuid
from datetime import date, datetime, timedelta, timezone

from app.models.exercise import Exercise
from app.models.gate import GateRank, GateStatus
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.services import gate_service
from app.services.gate_service import (
    GATE_XP,
    _rank_for_gain,
    _select_target_set,
    check_gate_clear,
    evaluate_gate_spawns,
)
from app.services.trend_service import projected_e1rm, weekly_best_e1rm_series, weekly_slope
from app.services.xp_service import get_or_create_user_progress

# ── Helpers ─────────────────────────────────────────────────────────────────

def _mk_user(create_test_user):
    return create_test_user(email=f"gate-{uuid.uuid4().hex[:8]}@example.com")[0]


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
    set_rows = []
    for n, (weight, reps) in enumerate(sets, start=1):
        s = Set(workout_exercise_id=we.id, weight=weight, reps=reps,
                set_number=n, e1rm=round(weight * (1 + reps / 30), 2))
        db.add(s)
        set_rows.append(s)
    db.commit()
    return workout, we, set_rows


def _seed_improving_bench(db, user_id, exercise, weeks=7, start_weight=200, step=5):
    """One bench workout per week, linearly improving; newest 2 days ago."""
    today = date.today()
    for i in range(weeks):
        days_ago = 2 + 7 * (weeks - 1 - i)
        when = datetime.combine(today - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=10)
        _mk_workout(db, user_id, exercise, when, sets=((start_weight + step * i, 5),))


def _patch_condition(monkeypatch, score):
    from app.services.condition_service import band_for_score

    def _fake(db, user_id, client_date=None, user_age=None):
        return {"score": score, "band": band_for_score(score),
                "generated_at": "", "inputs": [], "muscles_cooling": []}

    monkeypatch.setattr(gate_service, "compute_condition", _fake)


# ── Trend math (§6.1) ───────────────────────────────────────────────────────

def test_weekly_slope_requires_six_weeks():
    today = date.today()
    series = [(today - timedelta(weeks=i), 200.0 + i) for i in range(5)]
    assert weekly_slope(series) is None


def test_weekly_slope_linear_series():
    monday = date.today() - timedelta(days=date.today().weekday())
    # Perfect +5 lb/week over 6 consecutive weeks
    series = [(monday - timedelta(weeks=5 - i), 200.0 + 5 * i) for i in range(6)]
    assert weekly_slope(series) == 5.0


def test_projected_e1rm_math():
    assert projected_e1rm(250.0, 5.0, 14) == 260.0
    assert projected_e1rm(250.0, 3.5, 7) == 253.5


def test_weekly_best_series_aggregates_by_week(db, create_test_user):
    user = _mk_user(create_test_user)
    exercise = _mk_exercise(db)
    monday = date.today() - timedelta(days=date.today().weekday())
    # Two sessions in the same week — best should win
    for day_offset, weight in ((0, 200), (2, 210)):
        when = datetime.combine(monday + timedelta(days=day_offset), datetime.min.time())
        _mk_workout(db, user.id, exercise, when, sets=((weight, 5),))

    series = weekly_best_e1rm_series(db, user.id, [exercise.id])
    assert len(series) == 1
    assert series[0][0] == monday
    assert series[0][1] == round(210 * (1 + 5 / 30), 2)


# ── Ranking (§6.3) ──────────────────────────────────────────────────────────

def test_rank_bands():
    assert _rank_for_gain(101.5, 100.0, is_big_three=False) == GateRank.C
    assert _rank_for_gain(102.5, 100.0, is_big_three=False) == GateRank.B
    assert _rank_for_gain(104.0, 100.0, is_big_three=False) == GateRank.A
    assert _rank_for_gain(106.0, 100.0, is_big_three=False) == GateRank.S


def test_big_three_rank_bump_caps_at_s():
    assert _rank_for_gain(101.5, 100.0, is_big_three=True) == GateRank.B
    assert _rank_for_gain(106.0, 100.0, is_big_three=True) == GateRank.S


# ── Target selection (§6.2-5) ───────────────────────────────────────────────

def test_target_set_lands_in_band_with_5lb_increments():
    result = _select_target_set(271.0, 285.0, preferred_reps=5)
    assert result is not None
    weight, reps, e1rm = result
    assert weight % 5 == 0
    assert 1 <= reps <= 8
    assert 271.0 <= e1rm <= 285.0


def test_target_set_prefers_plate_milestone():
    # Band that contains 225×2 (e1rm 240.0) — milestone should win
    result = _select_target_set(238.0, 245.0, preferred_reps=2)
    assert result is not None
    assert result[0] == 225.0


def test_target_set_none_when_band_impossible():
    # Degenerate band narrower than any 5-lb/rep grid point
    assert _select_target_set(100.0, 100.05, preferred_reps=5) is None


# ── Spawn rules (§6.2) ──────────────────────────────────────────────────────

def test_spawn_on_improving_lift(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    exercise = _mk_exercise(db)
    _seed_improving_bench(db, user.id, exercise)
    _patch_condition(monkeypatch, 80)

    spawned = evaluate_gate_spawns(db, user.id)
    assert len(spawned) == 1
    gate = spawned[0]
    assert gate.status == GateStatus.OPEN.value
    assert gate.rank in ("C", "B", "A", "S")
    assert gate.target_e1rm >= gate.baseline_e1rm * 1.01
    assert gate.weekly_slope > 0
    assert gate.condition_at_spawn == 80
    assert "Gate" in gate.name and "×" in gate.name
    window = gate.expires_at - gate.spawned_at
    assert window.days == 14


def test_no_spawn_below_battle_ready(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    exercise = _mk_exercise(db)
    _seed_improving_bench(db, user.id, exercise)
    _patch_condition(monkeypatch, 50)

    assert evaluate_gate_spawns(db, user.id) == []


def test_no_spawn_with_under_six_weeks(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    exercise = _mk_exercise(db)
    _seed_improving_bench(db, user.id, exercise, weeks=4)
    _patch_condition(monkeypatch, 80)

    assert evaluate_gate_spawns(db, user.id) == []


def test_no_spawn_on_flat_trend(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    exercise = _mk_exercise(db)
    _seed_improving_bench(db, user.id, exercise, step=0)  # flat
    _patch_condition(monkeypatch, 80)

    assert evaluate_gate_spawns(db, user.id) == []


def test_no_duplicate_gate_per_lift(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    exercise = _mk_exercise(db)
    _seed_improving_bench(db, user.id, exercise)
    _patch_condition(monkeypatch, 80)

    first = evaluate_gate_spawns(db, user.id)
    assert len(first) == 1
    # Re-evaluate: same lift already has an open gate → nothing new
    assert evaluate_gate_spawns(db, user.id) == []


def test_stale_lift_never_spawns(db, create_test_user, monkeypatch):
    """6 improving weeks that ended a month ago must not project."""
    user = _mk_user(create_test_user)
    exercise = _mk_exercise(db)
    today = date.today()
    for i in range(7):
        days_ago = 35 + 7 * (6 - i)
        when = datetime.combine(today - timedelta(days=days_ago), datetime.min.time())
        _mk_workout(db, user.id, exercise, when, sets=((200 + 5 * i, 5),))
    _patch_condition(monkeypatch, 80)

    assert evaluate_gate_spawns(db, user.id) == []


# ── Lifecycle (§6.4) ────────────────────────────────────────────────────────

def _spawn_one(db, user, monkeypatch, exercise=None):
    if exercise is None:
        exercise = _mk_exercise(db)
    _seed_improving_bench(db, user.id, exercise)
    _patch_condition(monkeypatch, 80)
    spawned = evaluate_gate_spawns(db, user.id)
    assert len(spawned) == 1
    return exercise, spawned[0]


def test_clear_awards_xp_and_records_set(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    exercise, gate = _spawn_one(db, user, monkeypatch)
    progress = get_or_create_user_progress(db, user.id)
    xp_before = progress.total_xp
    workouts_before = progress.total_workouts

    # A set beating the target e1RM clears the gate
    target_weight = gate.target_weight + 10
    when = datetime.now(timezone.utc).replace(tzinfo=None)
    _, we, sets = _mk_workout(db, user.id, exercise, when,
                              sets=((target_weight, gate.target_reps),))
    cleared = check_gate_clear(db, user.id, we, sets)

    assert len(cleared) == 1
    db.commit()
    assert gate.status == GateStatus.CLEARED.value
    assert gate.cleared_by_set_id == sets[0].id
    assert gate.xp_awarded == GATE_XP[GateRank(gate.rank)]
    assert progress.total_xp == xp_before + gate.xp_awarded
    assert progress.total_workouts == workouts_before  # count_workout=False

    # Second identical set can't re-clear
    _, we2, sets2 = _mk_workout(db, user.id, exercise, when,
                                sets=((target_weight, gate.target_reps),))
    assert check_gate_clear(db, user.id, we2, sets2) == []


def test_below_target_set_does_not_clear(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    exercise, gate = _spawn_one(db, user, monkeypatch)

    when = datetime.now(timezone.utc).replace(tzinfo=None)
    _, we, sets = _mk_workout(db, user.id, exercise, when, sets=((100, 3),))
    assert check_gate_clear(db, user.id, we, sets) == []
    assert gate.status == GateStatus.OPEN.value


def test_overdue_gate_expires_quietly(db, create_test_user, monkeypatch):
    user = _mk_user(create_test_user)
    exercise, gate = _spawn_one(db, user, monkeypatch)
    # Force the window into the past
    gate.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    db.commit()

    evaluate_gate_spawns(db, user.id)
    assert gate.status == GateStatus.EXPIRED.value
    assert gate.xp_awarded is None


# ── Endpoints (§6.5) ────────────────────────────────────────────────────────

def test_get_gates_empty_for_new_user(client, db, auth_headers, unique_email):
    headers, _ = auth_headers(email=unique_email("gate"))
    resp = client.get("/gates", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_get_gates_spawns_and_returns_contract_shape(
    client, db, auth_headers, unique_email, monkeypatch
):
    headers, user = auth_headers(email=unique_email("gate"))
    exercise = _mk_exercise(db)
    _seed_improving_bench(db, user.id, exercise)
    _patch_condition(monkeypatch, 80)

    resp = client.get("/gates", headers=headers)
    assert resp.status_code == 200, resp.text
    gates = resp.json()
    assert len(gates) == 1
    gate = gates[0]
    assert set(gate) == {
        "id", "exercise_id", "exercise_name", "rank", "name",
        "target_weight", "target_reps", "target_e1rm", "baseline_e1rm",
        "projected_e1rm", "weekly_slope", "condition_at_spawn", "status",
        "spawned_at", "expires_at", "accepted_at", "cleared_at",
        "cleared_by_set_id", "xp_awarded",
    }
    assert gate["status"] == "open"
    assert gate["exercise_name"] == exercise.name


def test_accept_gate_lifecycle(client, db, auth_headers, unique_email, monkeypatch):
    headers, user = auth_headers(email=unique_email("gate"))
    exercise = _mk_exercise(db)
    _seed_improving_bench(db, user.id, exercise)
    _patch_condition(monkeypatch, 80)

    gate = client.get("/gates", headers=headers).json()[0]

    resp = client.post(f"/gates/{gate['id']}/accept", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"
    assert resp.json()["accepted_at"] is not None

    # Accepting again → 409 (only open gates can be accepted)
    assert client.post(f"/gates/{gate['id']}/accept", headers=headers).status_code == 409
    # Unknown id → 404
    assert client.post("/gates/nope/accept", headers=headers).status_code == 404


def test_gate_history_endpoint(client, db, auth_headers, unique_email, monkeypatch):
    headers, user = auth_headers(email=unique_email("gate"))
    exercise, gate = _spawn_one(db, user, monkeypatch, _mk_exercise(db))
    gate.status = GateStatus.EXPIRED.value
    db.commit()

    resp = client.get("/gates/history?limit=5", headers=headers)
    assert resp.status_code == 200, resp.text
    history = resp.json()
    assert len(history) == 1
    assert history[0]["status"] == "expired"

    # The expired gate left the live list. (The lift still projects a PR, so
    # GET /gates may legitimately respawn a fresh gate for it — expiry frees
    # the slot rather than blacklisting the lift.)
    live_ids = {g["id"] for g in client.get("/gates", headers=headers).json()}
    assert gate.id not in live_ids


def test_gates_require_auth(client):
    assert client.get("/gates").status_code in (401, 403)
    assert client.get("/gates/history").status_code in (401, 403)


# ── Directive rule 6 integration (§5.2-6) ───────────────────────────────────

def test_open_gate_produces_gate_reminder_directive(db, create_test_user, monkeypatch):
    from app.models.directive import DirectiveType
    from app.services import directive_service
    from app.services.directive_service import (
        check_directive_completion,
        get_or_generate_directive,
    )

    user = _mk_user(create_test_user)
    exercise, gate = _spawn_one(db, user, monkeypatch)

    # Keep training frequency >= 2/wk so rule 5 (VOLUME_LOW) doesn't outrank
    # rule 6 — the bench seed alone is 1 hunt/week.
    curls = _mk_exercise(db, name="Barbell Curl", primary="Biceps")
    today = date.today()
    for i, days_ago in enumerate((3, 8, 13, 18, 23)):
        when = datetime.combine(today - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=9)
        _mk_workout(db, user.id, curls, when, sets=((80 + i * 5, 8),))

    # Pin directive_service's condition too (independent import)
    from app.services.condition_service import band_for_score

    def _fake(db_, user_id, client_date=None, user_age=None):
        return {"score": 80, "band": band_for_score(80),
                "generated_at": "", "inputs": [], "muscles_cooling": []}

    monkeypatch.setattr(directive_service, "compute_condition", _fake)

    directive = get_or_generate_directive(db, user.id, date.today())
    assert directive.directive_type == DirectiveType.GATE_REMINDER.value
    assert gate.name in directive.message
    assert directive.params["gate_id"] == gate.id

    # Any set on that lift today completes it ("cleared or attempted")
    when = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=10)
    _mk_workout(db, user.id, exercise, when, sets=((100, 5),))
    assert check_directive_completion(db, user.id, date.today()) is not None
