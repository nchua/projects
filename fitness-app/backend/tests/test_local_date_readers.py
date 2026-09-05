"""
Tests for the ``local_date`` / ``weight_lb`` reader switch (ARISE v3 spec §12 0b).

A session stored at 2026-09-05T03:30Z (Saturday in UTC) that the client
stamped ``local_date = 2026-09-04`` (Friday night) must bucket into the
2026-08-31 week everywhere: the trend series, the weekly report, the
directive volume windows and the analytics weekly review. A NULL
``local_date`` row falls back consistently across readers (midnight → that
day; a real instant → its UTC day), and a kg set contributes lb tonnage.
"""
import uuid
from datetime import date, datetime, timedelta

from app.models.exercise import Exercise
from app.models.workout import Set, WeightUnit, WorkoutExercise, WorkoutSession
from app.services.directive_service import _volume_lb, _workouts_this_week
from app.services.training_load_service import (
    local_date_window_filter,
    local_day,
    session_local_day,
    set_weight_lb,
)
from app.services.trend_service import weekly_best_e1rm_series
from app.services.weekly_report_service import (
    _get_exercise_weekly_sets,
    generate_weekly_report,
)

WEEK_A = date(2026, 8, 31)     # Monday
WEEK_B = date(2026, 9, 7)      # next Monday
KG_TO_LB = 2.20462


def _user(create_test_user):
    return create_test_user(email=f"ld-{uuid.uuid4().hex[:8]}@example.com")[0]


def _exercise(db):
    ex = Exercise(id=str(uuid.uuid4()), name="Barbell Bench Press", category="compound",
                  primary_muscle="Chest", secondary_muscles=[], is_custom=False, user_id=None)
    db.add(ex)
    db.commit()
    return ex


def _session(db, user_id, exercise, instant, local_date, sets=((135, 5),), unit=WeightUnit.LB,
             warmup_sets=()):
    session = WorkoutSession(user_id=user_id, date=instant, local_date=local_date, duration_minutes=45)
    db.add(session)
    db.flush()
    we = WorkoutExercise(session_id=session.id, exercise_id=exercise.id, order_index=0)
    db.add(we)
    db.flush()
    n = 0
    for weight, reps in sets:
        n += 1
        weight_lb = round(weight * KG_TO_LB, 3) if unit == WeightUnit.KG else weight
        db.add(Set(workout_exercise_id=we.id, weight=weight, weight_unit=unit, weight_lb=weight_lb,
                   reps=reps, set_number=n, e1rm=round(weight_lb * (1 + reps / 30), 2)))
    for weight, reps in warmup_sets:
        n += 1
        db.add(Set(workout_exercise_id=we.id, weight=weight, weight_lb=weight, reps=reps,
                   set_number=n, is_warmup=True, e1rm=round(weight * (1 + reps / 30), 2)))
    db.commit()
    return session


# ── Helper semantics ────────────────────────────────────────────────────────

def test_local_day_precedence():
    stamped = date(2026, 9, 4)
    late_instant = datetime(2026, 9, 5, 3, 30)
    assert local_day(stamped, late_instant) == stamped                       # stamp wins
    assert local_day(None, datetime(2026, 9, 6, 0, 0)) == date(2026, 9, 6)   # midnight convention
    assert local_day(None, late_instant) == date(2026, 9, 5)                 # UTC day fallback
    assert local_day(None, None) is None


def test_set_weight_lb_prefers_backfilled_column():
    class _S:
        weight_lb = 220.462
        weight = 100.0
    assert set_weight_lb(_S()) == 220.462
    _S.weight_lb = None
    assert set_weight_lb(_S()) == 100.0


# ── Friday-night session stamped Friday, stored Saturday UTC ────────────────

def test_stamped_local_date_buckets_into_prior_week(db, create_test_user):
    user = _user(create_test_user)
    ex = _exercise(db)
    session = _session(db, user.id, ex, datetime(2026, 9, 5, 3, 30), date(2026, 9, 4),
                       sets=((185, 5),))
    assert session_local_day(session) == date(2026, 9, 4)

    # Trend series: one point, keyed by the Monday of the *local* week.
    series = weekly_best_e1rm_series(db, user.id, [ex.id])
    assert series == [(WEEK_A, round(185 * (1 + 5 / 30), 2))]

    # Weekly report: counted in WEEK_A, absent from WEEK_B.
    report_a = generate_weekly_report(db, user.id, week_start=WEEK_A, client_date=date(2026, 9, 9))
    report_b = generate_weekly_report(db, user.id, week_start=WEEK_B, client_date=date(2026, 9, 16))
    assert report_a.total_workouts == 1
    assert report_a.total_sets == 1
    assert report_a.total_volume == 925.0
    assert report_b.total_workouts == 0

    # Directive readers agree.
    assert _workouts_this_week(db, user.id, date(2026, 9, 6)) == 1      # Sunday of WEEK_A
    assert _workouts_this_week(db, user.id, date(2026, 9, 7)) == 0      # Monday of WEEK_B
    assert _volume_lb(db, user.id, [ex.id], WEEK_A, WEEK_A + timedelta(days=6)) == 925.0
    assert _get_exercise_weekly_sets(db, user.id, WEEK_A, WEEK_A + timedelta(days=6)) == {ex.id: 1}

    # SQL-level window filter agrees with the Python-side bucketing.
    in_week_a = (
        db.query(WorkoutSession.id)
        .filter(WorkoutSession.user_id == user.id,
                local_date_window_filter(WEEK_A, WEEK_A + timedelta(days=6)))
        .all()
    )
    assert [r[0] for r in in_week_a] == [session.id]


def test_stamped_local_date_beats_a_utc_instant_in_the_other_week(db, create_test_user):
    """A late-Sunday-local lift stored Monday 02:00Z, stamped Sunday, stays in
    the Sunday week; the same instant unstamped falls to its UTC day."""
    user = _user(create_test_user)
    ex = _exercise(db)
    stamped = _session(db, user.id, ex, datetime(2026, 9, 7, 2, 0), date(2026, 9, 6))
    legacy = _session(db, user.id, ex, datetime(2026, 9, 7, 2, 0), None)

    assert session_local_day(stamped) == date(2026, 9, 6)
    assert session_local_day(legacy) == date(2026, 9, 7)

    week_a = {r[0] for r in db.query(WorkoutSession.id).filter(
        WorkoutSession.user_id == user.id,
        local_date_window_filter(WEEK_A, WEEK_A + timedelta(days=6))).all()}
    week_b = {r[0] for r in db.query(WorkoutSession.id).filter(
        WorkoutSession.user_id == user.id,
        local_date_window_filter(WEEK_B, WEEK_B + timedelta(days=6))).all()}
    assert week_a == {stamped.id}
    assert week_b == {legacy.id}
    assert generate_weekly_report(db, user.id, week_start=WEEK_A).total_workouts == 1
    assert generate_weekly_report(db, user.id, week_start=WEEK_B).total_workouts == 1


def test_null_local_date_midnight_row_means_that_day(db, create_test_user):
    user = _user(create_test_user)
    ex = _exercise(db)
    # Manual/screenshot convention: midnight = "this local day".
    session = _session(db, user.id, ex, datetime(2026, 9, 6, 0, 0), None, sets=((200, 3),))
    assert session_local_day(session) == date(2026, 9, 6)
    assert weekly_best_e1rm_series(db, user.id, [ex.id])[0][0] == WEEK_A
    assert generate_weekly_report(db, user.id, week_start=WEEK_A).total_workouts == 1
    assert _workouts_this_week(db, user.id, date(2026, 9, 6)) == 1


# ── kg sets contribute lb tonnage ───────────────────────────────────────────

def test_kg_set_contributes_lb_tonnage_and_warmups_do_not(db, create_test_user):
    user = _user(create_test_user)
    ex = _exercise(db)
    _session(db, user.id, ex, datetime(2026, 9, 2, 18, 0), date(2026, 9, 2),
             sets=((100, 5),), unit=WeightUnit.KG, warmup_sets=((95, 5),))

    expected = round(round(100 * KG_TO_LB, 3) * 5, 2)   # ≈ 1102.31 lb
    report = generate_weekly_report(db, user.id, week_start=WEEK_A)
    assert report.total_volume == expected
    assert report.total_sets == 1                        # the warm-up is not volume
    assert round(_volume_lb(db, user.id, [ex.id], WEEK_A, WEEK_A + timedelta(days=6)), 2) == expected
    assert _get_exercise_weekly_sets(db, user.id, WEEK_A, WEEK_A + timedelta(days=6)) == {ex.id: 1}


def test_analytics_weekly_review_uses_local_days_and_lb(client, db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("ld"))
    ex = _exercise(db)
    # Friday-night local, Saturday UTC; kg set.
    _session(db, user.id, ex, datetime(2026, 9, 5, 3, 30), date(2026, 9, 4),
             sets=((100, 5),), unit=WeightUnit.KG)

    resp = client.get("/analytics/weekly-review?client_date=2026-09-06", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_workouts"] == 1
    assert data["total_volume"] == round(round(100 * KG_TO_LB, 3) * 5, 2)

    # The following Monday's review sees last week's session as "last week".
    resp = client.get("/analytics/weekly-review?client_date=2026-09-07", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_workouts"] == 0

    # The trend endpoint keys the data point by the local day.
    resp = client.get(f"/analytics/exercise/{ex.id}/trend?time_range=all", headers=headers)
    assert resp.status_code == 200, resp.text
    points = resp.json()["data_points"]
    assert [p["date"] for p in points] == ["2026-09-04"]
