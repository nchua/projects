"""
Tests for GET /calendar/weekly — the training-calendar PWA aggregation.

Covers: auth requirement, lift vs run classification, distance/mileage
totals, local-timezone day bucketing, and window edges.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.exercise import Exercise
from app.models.workout import Set, WorkoutExercise, WorkoutSession


def _utc_naive_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _monday_of(dt):
    d = dt.date()
    return d - timedelta(days=d.weekday())


@pytest.fixture
def calendar_user(db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("calendar"))
    return headers, user


def _add_lift(db, user_id, when, exercise, sets_spec):
    """sets_spec: list of (weight, reps, e1rm)."""
    session = WorkoutSession(user_id=user_id, date=when, name="Squat Day", duration_minutes=60)
    db.add(session)
    db.flush()
    we = WorkoutExercise(session_id=session.id, exercise_id=exercise.id, order_index=0)
    db.add(we)
    db.flush()
    for i, (weight, reps, e1rm) in enumerate(sets_spec):
        db.add(Set(
            workout_exercise_id=we.id, weight=weight, reps=reps,
            e1rm=e1rm, set_number=i + 1,
        ))
    db.commit()
    return session


def _add_run(db, user_id, when, meters, activity="Outdoor Run", hk_uuid=None,
             duration_seconds=None):
    session = WorkoutSession(
        user_id=user_id, date=when, duration_minutes=30,
        duration_seconds=duration_seconds,
        activity_type=activity, distance_meters=meters,
        hr_source="apple_watch", hk_uuid=hk_uuid,
        avg_heart_rate=150,
        notes=f"{activity} - Apple Watch | Distance: {meters}m" if meters else None,
    )
    db.add(session)
    db.commit()
    return session


@pytest.fixture
def squat(db):
    ex = Exercise(name="Back Squat", category="compound")
    db.add(ex)
    db.commit()
    return ex


class TestCalendarWeekly:
    def test_requires_auth(self, client):
        assert client.get("/calendar/weekly").status_code in (401, 403)

    def test_lifts_and_runs_bucketed(self, client, db, calendar_user, squat):
        headers, user = calendar_user
        now = _utc_naive_now()

        _add_lift(db, user.id, now - timedelta(hours=1), squat,
                  [(225, 5, 262.5), (245, 3, 269.5)])
        _add_run(db, user.id, now - timedelta(hours=2), 3218.7, hk_uuid="hk-run-1")
        # Non-run cardio must not count toward run mileage.
        _add_run(db, user.id, now - timedelta(hours=3), 15000.0,
                 activity="Outdoor Cycle", hk_uuid="hk-ride-1")

        resp = client.get("/calendar/weekly?weeks=2", headers=headers)
        assert resp.status_code == 200
        weeks = resp.json()["weeks"]
        assert len(weeks) == 2
        this_week = weeks[-1]

        assert this_week["lift_sessions"] == 1
        assert this_week["total_sets"] == 2
        lift = this_week["lifts"][0]
        assert lift["exercises"][0]["name"] == "Back Squat"
        assert lift["exercises"][0]["top_weight"] == 245
        assert lift["exercises"][0]["best_e1rm"] == 269.5
        assert lift["exercises"][0]["sets"][0] == {
            "weight": 225.0, "weight_unit": "lb", "reps": 5, "e1rm": 262.5,
        }

        runs = this_week["runs"]
        assert len(runs) == 2
        run = next(r for r in runs if r["is_run"])
        assert run["distance_miles"] == 2.0
        assert run["avg_heart_rate"] == 150
        # No exact seconds on this row -> pace falls back to rounded minutes:
        # 30 min over 2.0 mi = 900 sec/mi.
        assert run["pace_sec_per_mile"] == 900
        ride = next(r for r in runs if not r["is_run"])
        assert ride["activity_type"] == "Outdoor Cycle"
        # Weekly mileage counts runs only.
        assert this_week["run_miles"] == 2.0

    def test_old_sessions_fall_outside_window(self, client, db, calendar_user, squat):
        headers, user = calendar_user
        now = _utc_naive_now()
        _add_run(db, user.id, now - timedelta(weeks=6), 5000.0, hk_uuid="hk-old")

        resp = client.get("/calendar/weekly?weeks=2", headers=headers)
        assert resp.status_code == 200
        weeks = resp.json()["weeks"]
        assert all(w["runs"] == [] for w in weeks)

    def test_tz_offset_shifts_day_bucketing(self, client, db, calendar_user):
        headers, user = calendar_user
        now = _utc_naive_now()
        this_monday = _monday_of(now)

        # A run stored at Monday 02:00 UTC belongs to Sunday evening in
        # UTC-7 (offset 420) — i.e. the *previous* local week.
        run_utc = datetime.combine(this_monday, datetime.min.time()) + timedelta(hours=2)
        _add_run(db, user.id, run_utc, 1609.344, hk_uuid="hk-tz")

        utc_view = client.get("/calendar/weekly?weeks=2", headers=headers).json()["weeks"]
        utc_runs = [r for w in utc_view for r in w["runs"]]
        assert len(utc_runs) == 1
        assert utc_runs[0]["day_index"] == 0  # Monday in UTC

        pdt_view = client.get(
            "/calendar/weekly?weeks=3&tz_offset_minutes=420", headers=headers
        ).json()["weeks"]
        pdt_runs = [r for w in pdt_view for r in w["runs"]]
        # Appears exactly once, and shifted to Sunday (previous local day).
        assert len(pdt_runs) == 1
        assert pdt_runs[0]["day_index"] == 6
        assert sum(w["run_miles"] for w in pdt_view) == 1.0

    def test_midnight_sessions_keep_their_local_day(self, client, db, calendar_user, squat):
        """Manual/screenshot logs are stored at local midnight, not UTC.

        The tz offset must NOT shift them: a squat day logged for Saturday
        would otherwise render under Friday in the training-calendar PWA
        (regression: 2026-08-16).
        """
        headers, user = calendar_user
        now = _utc_naive_now()
        this_monday = _monday_of(now)

        # Saturday of the previous week, stored date-only style (midnight).
        saturday = this_monday - timedelta(days=2)
        stored = datetime.combine(saturday, datetime.min.time())
        _add_lift(db, user.id, stored, squat, [(225, 3, 247.5)])

        pdt_view = client.get(
            "/calendar/weekly?weeks=2&tz_offset_minutes=420", headers=headers
        ).json()["weeks"]
        lifts = [(w["week_start"], lift) for w in pdt_view for lift in w["lifts"]]
        assert len(lifts) == 1
        week_start, lift = lifts[0]
        assert week_start == (this_monday - timedelta(days=7)).isoformat()
        assert lift["day_index"] == 5  # Saturday, not Friday
        assert lift["local_date"] == saturday.isoformat()

    def test_pace_prefers_exact_seconds(self, client, db, calendar_user):
        headers, user = calendar_user
        now = _utc_naive_now()
        # 5 km in 29:17 -> 1757 s / 3.107 mi = 566 sec/mi (9:26).
        _add_run(db, user.id, now - timedelta(hours=1), 5000.0,
                 hk_uuid="hk-pace", duration_seconds=1757)

        resp = client.get("/calendar/weekly?weeks=1", headers=headers)
        run = resp.json()["weeks"][0]["runs"][0]
        assert run["duration_seconds"] == 1757
        assert run["pace_sec_per_mile"] == 566

    def test_soft_deleted_sessions_excluded(self, client, db, calendar_user):
        headers, user = calendar_user
        now = _utc_naive_now()
        s = _add_run(db, user.id, now - timedelta(hours=1), 2000.0, hk_uuid="hk-del")
        s.deleted_at = now
        db.commit()

        resp = client.get("/calendar/weekly?weeks=1", headers=headers)
        assert resp.json()["weeks"][0]["runs"] == []
