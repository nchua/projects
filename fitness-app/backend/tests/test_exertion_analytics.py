"""
Tests for ARISE v2 Phase 3 (spec §7, §10.2): strain unification, exertion
analytics endpoints, the cardio-screenshot HR upgrade, and the new
achievement requirement types.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

from app.core.exertion import compute_arise_strain
from app.models.exercise import Exercise
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.services.screenshot_service import parse_zone_seconds

# ── Helpers ─────────────────────────────────────────────────────────────────

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


def _mk_workout(db, user_id, exercise, when, sets=((135, 8),), **session_kwargs):
    workout = WorkoutSession(user_id=user_id, date=when, duration_minutes=45, **session_kwargs)
    db.add(workout)
    db.flush()
    we = WorkoutExercise(session_id=workout.id, exercise_id=exercise.id, order_index=0)
    db.add(we)
    db.flush()
    set_rows = []
    for n, entry in enumerate(sets, start=1):
        weight, reps = entry[0], entry[1]
        extra = entry[2] if len(entry) > 2 else {}
        s = Set(workout_exercise_id=we.id, weight=weight, reps=reps,
                set_number=n, e1rm=round(weight * (1 + reps / 30), 2), **extra)
        db.add(s)
        set_rows.append(s)
    db.commit()
    return workout


# ── §7.1 compute_arise_strain ───────────────────────────────────────────────

def test_arise_strain_prefers_whoop():
    result = compute_arise_strain(14.2, {"z3": 1200}, "whoop")
    assert result == {"value": 14.2, "source": "whoop"}


def test_arise_strain_screenshot_badge_for_screenshot_sessions():
    result = compute_arise_strain(12.0, None, "screenshot")
    assert result == {"value": 12.0, "source": "screenshot"}


def test_arise_strain_falls_back_to_exertion():
    result = compute_arise_strain(None, {"z5": 3600}, "apple_watch")
    assert result == {"value": 21.0, "source": "apple_watch"}


def test_arise_strain_null_without_hr_data():
    assert compute_arise_strain(None, None, None) is None
    assert compute_arise_strain(None, {}, "apple_watch") is None


# ── §7.3 zone parsing ───────────────────────────────────────────────────────

def test_parse_zone_seconds_mm_ss_and_zone_zero_dropped():
    zones = [
        {"zone": 0, "duration": "10:00"},   # below-zone time → dropped
        {"zone": 2, "duration": "15:30"},
        {"zone": 3, "duration": "1:02:00"}, # h:mm:ss
        {"zone": 4, "duration": "bogus"},   # unparseable → skipped
    ]
    assert parse_zone_seconds(zones) == {"z2": 930, "z3": 3720}


def test_parse_zone_seconds_empty_is_none():
    assert parse_zone_seconds(None) is None
    assert parse_zone_seconds([]) is None
    assert parse_zone_seconds([{"zone": 0, "duration": "5:00"}]) is None


# ── §7.1 workout payload addition ───────────────────────────────────────────

def test_workout_response_carries_arise_strain(client, db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("strain"))
    exercise = _mk_exercise(db)
    workout = _mk_workout(
        db, user.id, exercise,
        datetime.now(timezone.utc).replace(tzinfo=None),
        hr_zone_seconds={"z5": 3600},
        hr_source="apple_watch",
    )

    detail = client.get(f"/workouts/{workout.id}", headers=headers).json()
    assert detail["arise_strain"] == {"value": 21.0, "source": "apple_watch"}
    # Migration fields still present
    assert "exertion_score" in detail and "strain" in detail

    rows = client.get("/workouts?limit=5", headers=headers).json()
    assert rows[0]["arise_strain"] == {"value": 21.0, "source": "apple_watch"}


def test_workout_response_arise_strain_null_without_hr(client, db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("strain"))
    exercise = _mk_exercise(db)
    workout = _mk_workout(db, user.id, exercise, datetime.now(timezone.utc).replace(tzinfo=None))

    detail = client.get(f"/workouts/{workout.id}", headers=headers).json()
    assert detail["arise_strain"] is None


# ── §7.2-1 exertion weekly ──────────────────────────────────────────────────

def test_exertion_weekly_shape_and_aggregation(client, db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("exw"))
    exercise = _mk_exercise(db)
    monday = date.today() - timedelta(days=date.today().weekday())

    # Two workouts this week: one WHOOP strain, one zone-derived
    _mk_workout(db, user.id, exercise,
                datetime.combine(monday, datetime.min.time()) + timedelta(hours=10),
                sets=((100, 10),), strain=10.0)
    _mk_workout(db, user.id, exercise,
                datetime.combine(monday, datetime.min.time()) + timedelta(days=1, hours=10),
                sets=((200, 5),), hr_zone_seconds={"z3": 1800}, hr_source="apple_watch")

    resp = client.get("/analytics/exertion/weekly?weeks=4", headers=headers)
    assert resp.status_code == 200, resp.text
    points = resp.json()
    assert len(points) == 4  # continuous axis, empty weeks included

    current = points[-1]
    assert current["week_start"] == monday.isoformat()
    assert current["workout_count"] == 2
    assert current["volume_lb"] == 100 * 10 + 200 * 5
    # strain 10.0 + exertion for 30 min z3 (21*5400/18000 = 6.3)
    assert current["strain_total"] == 16.3
    assert current["strain_avg"] == 8.2
    assert current["zone_seconds"] == {"z3": 1800}

    empty_week = points[0]
    assert empty_week["workout_count"] == 0
    assert empty_week["strain_total"] is None
    assert empty_week["volume_lb"] == 0.0


# ── §7.2-2 cardiac cost ─────────────────────────────────────────────────────

def test_cardiac_cost_fallback_path_and_trend(client, db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("cc"))
    exercise = _mk_exercise(db)
    today = date.today()

    # Same matched set (185x5) across 3 weeks; peak HR falls week over week
    # while session avg stays 100 → ΔHR 60 → 50 → 40 (conditioning gain).
    for weeks_ago, peak in ((2, 160), (1, 150), (0, 140)):
        when = datetime.combine(today - timedelta(weeks=weeks_ago), datetime.min.time()) + timedelta(hours=10)
        _mk_workout(
            db, user.id, exercise, when,
            sets=((185, 5, {"peak_heart_rate": peak}),),
            avg_heart_rate=100,
        )

    resp = client.get(f"/analytics/exercise/{exercise.id}/cardiac-cost?weeks=8", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["exercise_id"] == exercise.id
    assert data["matched_set"] == {"weight": 185.0, "reps": 5}
    assert [p["delta_hr_median"] for p in data["points"]] == [60.0, 50.0, 40.0]
    assert data["percent_change"] == -33.3
    assert data["trend_direction"] == "improving"
    assert len(data["caveats"]) == 3


def test_cardiac_cost_insufficient_without_hr(client, db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("cc"))
    exercise = _mk_exercise(db)
    _mk_workout(db, user.id, exercise, datetime.now(timezone.utc).replace(tzinfo=None))

    resp = client.get(f"/analytics/exercise/{exercise.id}/cardiac-cost", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched_set"] is None
    assert data["points"] == []
    assert data["trend_direction"] == "insufficient_data"


def test_cardiac_cost_unknown_exercise_404(client, db, auth_headers, unique_email):
    headers, _ = auth_headers(email=unique_email("cc"))
    assert client.get("/analytics/exercise/nope/cardiac-cost", headers=headers).status_code == 404


# ── §7.3 activity save upgrade ──────────────────────────────────────────────

def test_save_activity_endpoint_persists_hr_richness(client, db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("act"))
    today = date.today()

    payload = {
        "activity_type": "RUNNING",
        "session_date": today.isoformat(),
        "duration_minutes": 42,
        "strain": 13.5,
        "calories": 480,
        "avg_hr": 152,
        "max_hr": 181,
        "heart_rate_zones": [
            {"zone": 2, "duration": "12:00"},
            {"zone": 3, "duration": "20:00"},
            {"zone": 4, "duration": "10:00"},
        ],
    }
    resp = client.post("/screenshot/save-activity", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["activity_saved"] is True

    workout = db.query(WorkoutSession).filter(
        WorkoutSession.id == data["workout_id"]
    ).first()
    assert workout.hr_source == "screenshot"
    assert workout.avg_heart_rate == 152
    assert workout.peak_heart_rate == 181
    assert workout.strain == 13.5
    assert workout.hr_zone_seconds == {"z2": 720, "z3": 1200, "z4": 600}
    assert workout.duration_minutes == 42

    # The unified strain badge for screenshot WHOOP activities is "screenshot"
    detail = client.get(f"/workouts/{workout.id}", headers=headers).json()
    assert detail["arise_strain"] == {"value": 13.5, "source": "screenshot"}


def test_save_activity_rejects_bad_date(client, db, auth_headers, unique_email):
    headers, _ = auth_headers(email=unique_email("act"))
    resp = client.post(
        "/screenshot/save-activity",
        json={"activity_type": "RUNNING", "session_date": "not-a-date"},
        headers=headers,
    )
    assert resp.status_code == 400


# ── §10.2 new achievement requirement types ─────────────────────────────────

def _seed_defs(db):
    from app.services.achievement_service import seed_achievement_definitions
    seed_achievement_definitions(db)


def test_gate_achievements_unlock(db, create_test_user):
    from app.models.gate import GateStatus, PRGate
    from app.services.achievement_service import check_and_unlock_achievements

    user, _ = create_test_user(email=f"ach-{uuid.uuid4().hex[:8]}@example.com")
    exercise = _mk_exercise(db)
    _seed_defs(db)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(PRGate(
        user_id=user.id, exercise_id=exercise.id, rank="S",
        name="S-Rank Gate: Bench 315×1", target_weight=315, target_reps=1,
        target_e1rm=325.5, baseline_e1rm=300.0, projected_e1rm=320.0,
        weekly_slope=4.0, condition_at_spawn=90,
        status=GateStatus.CLEARED.value, spawned_at=now, expires_at=now,
        cleared_at=now, xp_awarded=1200,
    ))
    db.commit()

    unlocked = check_and_unlock_achievements(db, user.id, {})
    ids = {a["id"] for a in unlocked}
    assert "gate_first" in ids          # >=1 cleared
    assert "gate_s_rank" in ids         # S-rank cleared
    assert "gate_5" not in ids          # only 1 cleared


def test_directive_streak_achievement(db, create_test_user):
    from app.models.directive import DirectiveType, UserDirective
    from app.services.achievement_service import _directive_streak, check_and_unlock_achievements

    user, _ = create_test_user(email=f"ach-{uuid.uuid4().hex[:8]}@example.com")
    _seed_defs(db)
    today = date.today()

    # 7 consecutive completed directives ending yesterday; today's pending
    for offset in range(1, 8):
        db.add(UserDirective(
            user_id=user.id, date=today - timedelta(days=offset),
            directive_type=DirectiveType.MAINTAIN.value, message="m",
            is_completed=True, completed_at=datetime.now(timezone.utc),
        ))
    db.add(UserDirective(
        user_id=user.id, date=today,
        directive_type=DirectiveType.MAINTAIN.value, message="m",
        is_completed=False,
    ))
    db.commit()

    assert _directive_streak(db, user.id) == 7
    unlocked = check_and_unlock_achievements(db, user.id, {})
    ids = {a["id"] for a in unlocked}
    assert "directive_7" in ids
    assert "directive_30" not in ids


def test_directive_streak_broken_by_gap(db, create_test_user):
    from app.models.directive import DirectiveType, UserDirective
    from app.services.achievement_service import _directive_streak

    user, _ = create_test_user(email=f"ach-{uuid.uuid4().hex[:8]}@example.com")
    today = date.today()
    # Completed yesterday and 3 days ago — the gap at day-2 breaks the streak
    for offset in (1, 3):
        db.add(UserDirective(
            user_id=user.id, date=today - timedelta(days=offset),
            directive_type=DirectiveType.MAINTAIN.value, message="m",
            is_completed=True, completed_at=datetime.now(timezone.utc),
        ))
    db.commit()
    assert _directive_streak(db, user.id) == 1


def test_strain_18_achievement(db, create_test_user):
    from app.services.achievement_service import check_and_unlock_achievements

    user, _ = create_test_user(email=f"ach-{uuid.uuid4().hex[:8]}@example.com")
    exercise = _mk_exercise(db)
    _seed_defs(db)

    _mk_workout(db, user.id, exercise,
                datetime.now(timezone.utc).replace(tzinfo=None),
                strain=18.4)

    unlocked = check_and_unlock_achievements(db, user.id, {})
    assert "strain_18" in {a["id"] for a in unlocked}


# ── QA-pass regression tests (2026-07-12 /evaluate findings) ────────────────

def test_pure_cardio_activity_completes_directive(client, db, auth_headers, unique_email):
    """A scanned run with no strength exercises still counts as a hunt (§5.2)."""
    from app.models.directive import DirectiveType, UserDirective

    headers, user = auth_headers(email=unique_email("actdir"))
    today = date.today()
    db.add(UserDirective(
        user_id=user.id, date=today,
        directive_type=DirectiveType.MAINTAIN.value, message="m",
    ))
    db.commit()

    resp = client.post(
        "/screenshot/save-activity",
        json={"activity_type": "RUNNING", "session_date": today.isoformat(),
              "duration_minutes": 30},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    directive = db.query(UserDirective).filter(UserDirective.user_id == user.id).first()
    assert directive.is_completed is True


def test_directive_streak_tolerates_client_server_day_drift(db, create_test_user):
    """A pending newest directive dated 'yesterday' server-time is the
    client's in-progress today under UTC drift — it must not zero the streak."""
    from app.models.directive import DirectiveType, UserDirective
    from app.services.achievement_service import _directive_streak

    user, _ = create_test_user(email=f"drift-{uuid.uuid4().hex[:8]}@example.com")
    today = date.today()

    # Pending directive dated yesterday (server ahead of client), preceded by
    # 3 consecutive completed days.
    db.add(UserDirective(
        user_id=user.id, date=today - timedelta(days=1),
        directive_type=DirectiveType.MAINTAIN.value, message="m",
        is_completed=False,
    ))
    for offset in (2, 3, 4):
        db.add(UserDirective(
            user_id=user.id, date=today - timedelta(days=offset),
            directive_type=DirectiveType.MAINTAIN.value, message="m",
            is_completed=True, completed_at=datetime.now(timezone.utc),
        ))
    db.commit()

    assert _directive_streak(db, user.id) == 3


def test_out_of_scale_strain_dropped_on_activity_save(db, create_test_user):
    """Non-WHOOP effort metrics (e.g. Garmin Training Load 250) are never
    persisted as strain (§7.3) — the auto-save path validates server-side."""
    import asyncio

    from app.models.activity import DailyActivity
    from app.services.screenshot_service import save_whoop_activity

    user, _ = create_test_user(email=f"scale-{uuid.uuid4().hex[:8]}@example.com")
    activity_id, workout_id = asyncio.run(
        save_whoop_activity(
            db, user.id,
            {"activity_type": "RUNNING", "strain": 250.0, "duration_minutes": 40},
        )
    )

    workout = db.query(WorkoutSession).filter(WorkoutSession.id == workout_id).first()
    assert workout.strain is None

    activity = db.query(DailyActivity).filter(DailyActivity.id == activity_id).first()
    assert activity.strain is None
