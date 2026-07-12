"""
Tests for the Hunter Condition service (ARISE v2 spec §4).

Covers the normalization formulas, the renormalization (graceful-degradation)
rule, band mapping, WHOOP-row preference across multi-source days, the
yesterday-strain exertion fallback, and the GET /condition endpoint shape.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

from app.models.activity import DailyActivity
from app.models.exercise import Exercise
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.services.condition_service import (
    BAND_BATTLE_READY,
    BAND_CRITICAL,
    BAND_PEAK,
    BAND_STRAINED,
    CONDITION_WEIGHTS,
    _freshness_subscore,
    _strain_subscore,
    band_for_score,
    compute_condition,
)

# ── Pure-formula unit tests ─────────────────────────────────────────────────

def test_band_thresholds():
    assert band_for_score(100) == BAND_PEAK
    assert band_for_score(85) == BAND_PEAK
    assert band_for_score(84) == BAND_BATTLE_READY
    assert band_for_score(65) == BAND_BATTLE_READY
    assert band_for_score(64) == BAND_STRAINED
    assert band_for_score(40) == BAND_STRAINED
    assert band_for_score(39) == BAND_CRITICAL
    assert band_for_score(0) == BAND_CRITICAL


def test_strain_subscore_neutral_below_10():
    assert _strain_subscore(0.0) == 100
    assert _strain_subscore(10.0) == 100


def test_strain_subscore_linear_to_40_at_21():
    assert _strain_subscore(21.0) == 40
    # Midpoint 15.5 → 100 - 30 = 70
    assert _strain_subscore(15.5) == 70


def test_freshness_all_fresh_is_100():
    assert _freshness_subscore([]) == 100


def test_freshness_counts_remaining_fatigue_over_8_muscles():
    # One muscle 50% recovered → 50 remaining / 8 muscles = 6.25 → 94
    cooling = [{"status": "cooling", "cooldown_percent": 50.0}]
    assert _freshness_subscore(cooling) == 94
    # Ready entries (include_ready shape) must not count as fatigue
    cooling.append({"status": "ready", "cooldown_percent": 100.0})
    assert _freshness_subscore(cooling) == 94


# ── DB-backed integration tests ─────────────────────────────────────────────

def _add_activity(db, user_id, day, source="whoop_screenshot", **fields):
    row = DailyActivity(user_id=user_id, date=day, source=source, **fields)
    db.add(row)
    db.commit()
    return row


def test_condition_with_no_data_leans_on_freshness(db, create_test_user):
    user, _ = create_test_user(email=f"cond-{uuid.uuid4().hex[:8]}@example.com")
    result = compute_condition(db, user.id, date.today())

    # Only muscle freshness is available → fully fresh → 100, PEAK
    assert result["score"] == 100
    assert result["band"] == BAND_PEAK

    by_key = {i["key"]: i for i in result["inputs"]}
    assert set(by_key) == set(CONDITION_WEIGHTS)
    assert by_key["cooldowns"]["available"] is True
    assert by_key["cooldowns"]["effective_weight"] == 1.0
    for key in ("recovery", "sleep", "strain_yesterday", "rhr_trend"):
        assert by_key[key]["available"] is False
        assert by_key[key]["subscore"] is None
        assert by_key[key]["effective_weight"] == 0.0


def test_condition_renormalizes_weights(db, create_test_user):
    user, _ = create_test_user(email=f"cond-{uuid.uuid4().hex[:8]}@example.com")
    today = date.today()
    _add_activity(db, user.id, today, recovery_score=50)

    result = compute_condition(db, user.id, today)
    by_key = {i["key"]: i for i in result["inputs"]}

    # recovery (0.40) + cooldowns (0.25) available → weights renormalize
    assert by_key["recovery"]["effective_weight"] == round(0.40 / 0.65, 4)
    assert by_key["cooldowns"]["effective_weight"] == round(0.25 / 0.65, 4)
    # score = (50*0.40 + 100*0.25) / 0.65 ≈ 69
    assert result["score"] == 69
    assert result["band"] == BAND_BATTLE_READY


def test_sleep_normalization_anchors(db, create_test_user):
    user, _ = create_test_user(email=f"cond-{uuid.uuid4().hex[:8]}@example.com")
    today = date.today()
    _add_activity(db, user.id, today, sleep_hours=5.75)

    result = compute_condition(db, user.id, today)
    by_key = {i["key"]: i for i in result["inputs"]}
    # (5.75 - 4.0) / 3.5 = 0.5 → 50
    assert by_key["sleep"]["subscore"] == 50
    assert by_key["sleep"]["raw"] == 5.75


def test_whoop_row_preferred_over_apple_fitness(db, create_test_user):
    user, _ = create_test_user(email=f"cond-{uuid.uuid4().hex[:8]}@example.com")
    today = date.today()
    _add_activity(db, user.id, today, source="apple_fitness", sleep_hours=4.0)
    _add_activity(db, user.id, today, source="whoop_screenshot", sleep_hours=7.5)

    result = compute_condition(db, user.id, today)
    by_key = {i["key"]: i for i in result["inputs"]}
    assert by_key["sleep"]["raw"] == 7.5
    assert by_key["sleep"]["subscore"] == 100
    assert by_key["sleep"]["source"] == "whoop"


def test_yesterday_strain_from_whoop(db, create_test_user):
    user, _ = create_test_user(email=f"cond-{uuid.uuid4().hex[:8]}@example.com")
    today = date.today()
    _add_activity(db, user.id, today - timedelta(days=1), strain=15.5)

    result = compute_condition(db, user.id, today)
    by_key = {i["key"]: i for i in result["inputs"]}
    assert by_key["strain_yesterday"]["subscore"] == 70
    assert by_key["strain_yesterday"]["source"] == "whoop"


def test_yesterday_strain_falls_back_to_exertion(db, create_test_user):
    user, _ = create_test_user(email=f"cond-{uuid.uuid4().hex[:8]}@example.com")
    today = date.today()
    yesterday = datetime.combine(today - timedelta(days=1), datetime.min.time()) + timedelta(hours=18)
    # One hour in z5 → weighted 18000 s → exertion 21.0 → subscore 40
    workout = WorkoutSession(
        user_id=user.id,
        date=yesterday,
        duration_minutes=60,
        hr_source="apple_watch",
        hr_zone_seconds={"z5": 3600},
    )
    db.add(workout)
    db.commit()

    result = compute_condition(db, user.id, today)
    by_key = {i["key"]: i for i in result["inputs"]}
    assert by_key["strain_yesterday"]["raw"] == 21.0
    assert by_key["strain_yesterday"]["subscore"] == 40
    assert by_key["strain_yesterday"]["source"] == "apple_watch"


def test_rhr_trend_elevated_and_floor(db, create_test_user):
    user, _ = create_test_user(email=f"cond-{uuid.uuid4().hex[:8]}@example.com")
    today = date.today()
    for offset in (1, 2, 3):
        _add_activity(db, user.id, today - timedelta(days=offset), resting_heart_rate=55)
    _add_activity(db, user.id, today, resting_heart_rate=59)

    result = compute_condition(db, user.id, today)
    by_key = {i["key"]: i for i in result["inputs"]}
    # today 59 vs mean 55 → 100 - 40 = 60
    assert by_key["rhr_trend"]["subscore"] == 60

    # Below-mean RHR never boosts above 100; big elevation floors at 40
    row = db.query(DailyActivity).filter(
        DailyActivity.user_id == user.id, DailyActivity.date == today
    ).first()
    row.resting_heart_rate = 75
    db.commit()
    result = compute_condition(db, user.id, today)
    by_key = {i["key"]: i for i in result["inputs"]}
    assert by_key["rhr_trend"]["subscore"] == 40


def test_muscle_fatigue_lowers_freshness(db, create_test_user):
    user, _ = create_test_user(email=f"cond-{uuid.uuid4().hex[:8]}@example.com")
    exercise = Exercise(
        id=str(uuid.uuid4()),
        name="Barbell Bench Press",
        category="compound",
        primary_muscle="Chest",
        secondary_muscles=["Triceps", "Shoulders"],
        is_custom=False,
        user_id=None,
    )
    db.add(exercise)
    db.flush()
    workout = WorkoutSession(
        user_id=user.id,
        date=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2),
        duration_minutes=45,
    )
    db.add(workout)
    db.flush()
    we = WorkoutExercise(session_id=workout.id, exercise_id=exercise.id, order_index=0)
    db.add(we)
    db.flush()
    for n in range(1, 5):
        db.add(Set(workout_exercise_id=we.id, weight=185, reps=5, set_number=n, e1rm=215.0))
    db.commit()

    result = compute_condition(db, user.id, date.today())
    by_key = {i["key"]: i for i in result["inputs"]}
    assert by_key["cooldowns"]["subscore"] < 100
    assert len(result["muscles_cooling"]) > 0


# ── Endpoint tests ──────────────────────────────────────────────────────────

def test_get_condition_endpoint_shape(client, db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("cond"))
    resp = client.get("/condition", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert set(data) == {"score", "band", "generated_at", "inputs", "muscles_cooling"}
    assert isinstance(data["score"], int)
    assert data["band"] in ("peak", "battle_ready", "strained", "critical")
    assert len(data["inputs"]) == 5
    for entry in data["inputs"]:
        assert set(entry) == {
            "key", "label", "raw", "subscore", "weight",
            "effective_weight", "available", "source",
        }


def test_get_condition_endpoint_accepts_client_date(client, db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("cond"))
    target = date.today() - timedelta(days=1)
    _add_activity(db, user.id, target, recovery_score=80)

    resp = client.get(f"/condition?client_date={target.isoformat()}", headers=headers)
    assert resp.status_code == 200
    by_key = {i["key"]: i for i in resp.json()["inputs"]}
    assert by_key["recovery"]["available"] is True
    assert by_key["recovery"]["raw"] == 80

    # Malformed client_date falls back to server today instead of erroring
    resp = client.get("/condition?client_date=not-a-date", headers=headers)
    assert resp.status_code == 200


def test_get_condition_requires_auth(client):
    assert client.get("/condition").status_code in (401, 403)
