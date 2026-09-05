"""
Tests for the training-load service (ARISE v3 spec §6.1–6.3, §15.4).

Covers the per-session formulas (TRIMP, session-RPE and their estimated
fallbacks), the run-only mileage rule, the EWMA cold start (ACWR null on day
27, a number on day 28), every §6.3 flag at its boundary, deload_due from
both sources, recompute idempotency, miles_plan_7d from the plan, and the
GET /load contract.
"""
import uuid
from datetime import date, datetime, time, timedelta

from app.models.campaign import Campaign, CampaignArc, HuntTemplate, PlannedHunt
from app.models.exercise import Exercise
from app.models.training_load import DailyTrainingLoad
from app.models.workout import Set, WeightUnit, WorkoutExercise, WorkoutSession
from app.services import training_load_service as tls
from app.services.training_load_service import (
    FLAG_DELOAD_DUE,
    FLAG_LONG_RUN_SHARE,
    FLAG_RAMP_HIGH,
    FLAG_RUN_ACWR_CRITICAL,
    FLAG_RUN_ACWR_HIGH,
    arc_deload_week,
    deload_due_for_week,
    flags_for_day,
    get_load_state,
    guard_flags_for_date,
    recompute_daily_load,
    session_load,
    session_miles,
    trimp,
)

TODAY = date(2026, 9, 5)          # Saturday
MONDAY = date(2026, 8, 31)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _user(create_test_user):
    return create_test_user(email=f"load-{uuid.uuid4().hex[:8]}@example.com")[0]


def _exercise(db, name="Barbell Bench Press"):
    ex = Exercise(id=str(uuid.uuid4()), name=name, category="compound",
                  primary_muscle="Chest", secondary_muscles=[], is_custom=False, user_id=None)
    db.add(ex)
    db.commit()
    return ex


def _cardio(db, user_id, day, *, miles=None, minutes=None, zones=None,
            activity="Outdoor Run", stamp_local=True):
    session = WorkoutSession(
        user_id=user_id,
        date=datetime.combine(day, time(7, 30)),
        local_date=day if stamp_local else None,
        duration_minutes=minutes,
        activity_type=activity,
        distance_meters=miles * tls.METERS_PER_MILE if miles is not None else None,
        hr_zone_seconds=zones,
        hr_source="apple_watch" if zones else None,
    )
    db.add(session)
    db.commit()
    return session


def _lift(db, user_id, exercise, day, *, sets=((225, 5), (225, 5), (225, 5)),
          set_rpes=None, session_rpe=None, minutes=60, warmups=0):
    session = WorkoutSession(
        user_id=user_id,
        date=datetime.combine(day, time(18, 0)),
        local_date=day,
        duration_minutes=minutes,
        session_rpe=session_rpe,
    )
    db.add(session)
    db.flush()
    we = WorkoutExercise(session_id=session.id, exercise_id=exercise.id, order_index=0)
    db.add(we)
    db.flush()
    n = 0
    for _ in range(warmups):
        n += 1
        db.add(Set(workout_exercise_id=we.id, weight=95, weight_lb=95, reps=5,
                   set_number=n, is_warmup=True))
    for i, (weight, reps) in enumerate(sets):
        n += 1
        db.add(Set(workout_exercise_id=we.id, weight=weight, weight_unit=WeightUnit.LB,
                   weight_lb=weight, reps=reps, set_number=n,
                   rpe=set_rpes[i] if set_rpes else None,
                   e1rm=round(weight * (1 + reps / 30), 2)))
    db.commit()
    return session


def _loaded(db, session_id):
    return db.query(WorkoutSession).filter(WorkoutSession.id == session_id).first()


def _row(db, user_id, day):
    return (
        db.query(DailyTrainingLoad)
        .filter(DailyTrainingLoad.user_id == user_id, DailyTrainingLoad.local_date == day)
        .first()
    )


# ── §6.1 formulas ───────────────────────────────────────────────────────────

def test_trimp_arithmetic():
    # 10 min z1 + 20 min z2 + 5 min z3 = 10 + 40 + 15
    assert trimp({"z1": 600, "z2": 1200, "z3": 300}) == 65.0
    assert trimp({"z5": 3600}) == 300.0
    assert trimp(None) is None
    assert trimp({"z2": 0, "bogus": 100}) is None


def test_cardio_with_zones_is_trimp_not_estimated(db, create_test_user):
    user = _user(create_test_user)
    s = _cardio(db, user.id, TODAY, miles=3, minutes=30, zones={"z2": 900, "z3": 900})
    assert session_load(_loaded(db, s.id)) == (75.0, False)


def test_cardio_without_zones_is_duration_times_2_5_estimated(db, create_test_user):
    user = _user(create_test_user)
    s = _cardio(db, user.id, TODAY, miles=4, minutes=40)
    assert session_load(_loaded(db, s.id)) == (100.0, True)


def test_whoop_strain_never_enters_load(db, create_test_user):
    user = _user(create_test_user)
    s = _cardio(db, user.id, TODAY, miles=4, minutes=40)
    s.strain = 18.5
    db.commit()
    assert session_load(_loaded(db, s.id)) == (100.0, True)


def test_lift_session_rpe_wins_over_set_rpes(db, create_test_user):
    user = _user(create_test_user)
    ex = _exercise(db)
    s = _lift(db, user.id, ex, TODAY, session_rpe=8, set_rpes=[6, 6, 6], minutes=60)
    assert session_load(_loaded(db, s.id)) == (480.0, False)


def test_lift_mean_set_rpe_when_no_session_rpe(db, create_test_user):
    user = _user(create_test_user)
    ex = _exercise(db)
    s = _lift(db, user.id, ex, TODAY, set_rpes=[7, 9, 8], minutes=45)
    assert session_load(_loaded(db, s.id)) == (360.0, False)


def test_lift_without_rpe_is_sets_x6_estimated_and_ignores_warmups(db, create_test_user):
    user = _user(create_test_user)
    ex = _exercise(db)
    s = _lift(db, user.id, ex, TODAY, minutes=60, warmups=2)   # 3 working + 2 warm-ups
    assert session_load(_loaded(db, s.id)) == (18.0, True)


def test_lift_without_duration_assumes_45_minutes(db, create_test_user):
    user = _user(create_test_user)
    ex = _exercise(db)
    s = _lift(db, user.id, ex, TODAY, minutes=None, session_rpe=8)
    assert session_load(_loaded(db, s.id)) == (360.0, True)


def test_walks_do_not_add_miles(db, create_test_user):
    user = _user(create_test_user)
    walk = _cardio(db, user.id, TODAY, miles=2.5, minutes=50, activity="Outdoor Walk")
    run = _cardio(db, user.id, TODAY - timedelta(days=1), miles=2.5, minutes=25)
    assert session_miles(walk) == 0.0
    assert round(session_miles(run), 3) == 2.5
    assert tls.is_run_session(walk) is False
    assert tls.is_run_session(run) is True

    recompute_daily_load(db, user.id, as_of=TODAY)
    assert _row(db, user.id, TODAY).miles == 0.0
    assert round(_row(db, user.id, TODAY - timedelta(days=1)).miles, 3) == 2.5
    # The walk still carries load (it's cardio), just not run load.
    assert _row(db, user.id, TODAY).total_load == 125.0
    assert _row(db, user.id, TODAY).run_load == 0.0


# ── §6.2 series: EWMA cold start ────────────────────────────────────────────

def test_run_acwr_null_on_day_27_number_on_day_28(db, create_test_user):
    user = _user(create_test_user)
    first = TODAY - timedelta(days=28)
    for i in range(29):
        _cardio(db, user.id, first + timedelta(days=i), miles=3, minutes=30,
                zones={"z2": 1800})
    recompute_daily_load(db, user.id, as_of=TODAY)

    day27 = _row(db, user.id, TODAY - timedelta(days=1))
    day28 = _row(db, user.id, TODAY)
    assert day27.run_acwr is None
    assert day27.run_chronic_28d > 0
    # Constant daily load → bias-corrected EWMAs are exactly equal → 1.0.
    assert day28.run_acwr == 1.0
    assert day28.total_acwr == 1.0
    assert day28.run_acute_7d == 60.0
    assert day28.miles_7d == 21.0
    assert day28.longest_run_7d == 3.0
    assert day28.flags == []


def test_lifts_never_enter_run_acwr(db, create_test_user):
    user = _user(create_test_user)
    ex = _exercise(db)
    first = TODAY - timedelta(days=28)
    for i in range(29):
        _cardio(db, user.id, first + timedelta(days=i), miles=3, minutes=30, zones={"z2": 1800})
    # A brutal lifting weekend on the last two days.
    _lift(db, user.id, ex, TODAY - timedelta(days=1), session_rpe=10, minutes=120)
    _lift(db, user.id, ex, TODAY, session_rpe=10, minutes=120)
    recompute_daily_load(db, user.id, as_of=TODAY)

    row = _row(db, user.id, TODAY)
    assert row.run_acwr == 1.0          # unchanged by the lifts
    assert row.total_acwr > 1.5         # total load did spike
    assert row.lift_load == 1200.0
    assert FLAG_RUN_ACWR_HIGH not in row.flags


# ── §6.3 rules at the boundary ──────────────────────────────────────────────

def _flags(**overrides):
    base = dict(miles_7d=0.0, miles_plan_7d=None, longest_run_7d=0.0,
                run_acwr=None, deload_due=False)
    base.update(overrides)
    return flags_for_day(**base)


def test_ramp_high_boundary():
    assert FLAG_RAMP_HIGH not in _flags(miles_7d=12.0, miles_plan_7d=10.0)   # = 1.20 × plan
    assert FLAG_RAMP_HIGH in _flags(miles_7d=12.1, miles_plan_7d=10.0)       # 1.21 ×
    assert FLAG_RAMP_HIGH not in _flags(miles_7d=8.0, miles_plan_7d=6.0)     # > 1.2× but not > 8
    assert FLAG_RAMP_HIGH in _flags(miles_7d=8.1, miles_plan_7d=6.0)
    assert FLAG_RAMP_HIGH not in _flags(miles_7d=30.0, miles_plan_7d=None)   # needs a plan


def test_long_run_share_boundary():
    assert FLAG_LONG_RUN_SHARE not in _flags(miles_7d=14.9, longest_run_7d=10.0)
    assert FLAG_LONG_RUN_SHARE not in _flags(miles_7d=15.0, longest_run_7d=6.0)   # = 40%
    assert FLAG_LONG_RUN_SHARE in _flags(miles_7d=15.0, longest_run_7d=6.1)


def test_run_acwr_boundaries():
    assert _flags(run_acwr=1.30) == []
    assert _flags(run_acwr=1.31) == [FLAG_RUN_ACWR_HIGH]
    assert _flags(run_acwr=1.50) == [FLAG_RUN_ACWR_HIGH]
    assert _flags(run_acwr=1.51) == [FLAG_RUN_ACWR_HIGH, FLAG_RUN_ACWR_CRITICAL]
    assert _flags(run_acwr=None) == []


def test_deload_due_flag_and_band():
    assert _flags(deload_due=True) == [FLAG_DELOAD_DUE]
    assert tls.band_for_acwr(None) == "cold_start"
    assert tls.band_for_acwr(1.30) == "ok"
    assert tls.band_for_acwr(1.31) == "high"
    assert tls.band_for_acwr(1.51) == "critical"


# ── deload_due sources ──────────────────────────────────────────────────────

def _campaign(db, user_id, start, *, weeks=12, cadence=4, overrides=None):
    campaign = Campaign(user_id=user_id, name="Base", start_date=start, overrides=overrides)
    db.add(campaign)
    db.flush()
    arc = CampaignArc(campaign_id=campaign.id, index=0, name="Arc 1", weeks=weeks,
                      run_miles_min=10, run_miles_max=20, long_run_miles=6,
                      deload_every_n_weeks=cadence, deload_factor=0.75)
    db.add(arc)
    db.commit()
    db.refresh(campaign)
    return campaign, arc


def test_deload_due_from_arc_cadence(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    start = MONDAY - timedelta(weeks=7)
    campaign, _ = _campaign(db, user.id, start, cadence=4)
    monkeypatch.setattr(tls, "_progression_verdicts", lambda db_, uid, ws: [])

    assert arc_deload_week(campaign, start + timedelta(weeks=3)) is True    # week 4
    assert arc_deload_week(campaign, start + timedelta(weeks=7)) is True    # week 8
    assert arc_deload_week(campaign, start + timedelta(weeks=2)) is False
    assert arc_deload_week(campaign, start + timedelta(weeks=12)) is False  # past the arc
    # Through the service (active-campaign fallback query finds the row).
    assert deload_due_for_week(db, user.id, start + timedelta(weeks=3)) is True
    assert deload_due_for_week(db, user.id, start + timedelta(weeks=2)) is False


def test_deload_due_honors_override_deload_weeks(db, create_test_user):
    user = _user(create_test_user)
    week = MONDAY - timedelta(weeks=1)
    campaign, _ = _campaign(db, user.id, MONDAY - timedelta(weeks=5), cadence=8,
                            overrides={"deload_weeks": [week.isoformat()]})
    assert arc_deload_week(campaign, week) is True


def test_deload_due_from_two_deload_lift_verdicts(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    monkeypatch.setattr(tls, "_get_active_campaign", lambda db_, uid: None)

    verdicts = [{"family_id": "back_squat", "verdict": "deload_lift"},
                {"family_id": "bench_press", "verdict": "progress"}]
    monkeypatch.setattr(tls, "_progression_verdicts", lambda db_, uid, ws: verdicts)
    assert deload_due_for_week(db, user.id, MONDAY) is False

    verdicts.append({"family_id": "deadlift", "verdict": "deload_lift"})
    assert deload_due_for_week(db, user.id, MONDAY) is True

    _cardio(db, user.id, TODAY, miles=3, minutes=30)
    recompute_daily_load(db, user.id, as_of=TODAY)
    assert _row(db, user.id, TODAY).flags == [FLAG_DELOAD_DUE]


# ── Persistence ─────────────────────────────────────────────────────────────

def test_recompute_writes_35_days_and_is_idempotent(db, create_test_user):
    user = _user(create_test_user)
    ex = _exercise(db)
    s1 = _cardio(db, user.id, TODAY - timedelta(days=3), miles=5, minutes=50, zones={"z2": 3000})
    s2 = _lift(db, user.id, ex, TODAY, session_rpe=7, minutes=60)

    recompute_daily_load(db, user.id, as_of=TODAY)
    rows = db.query(DailyTrainingLoad).filter(DailyTrainingLoad.user_id == user.id).all()
    assert len(rows) == 35
    assert min(r.local_date for r in rows) == TODAY - timedelta(days=34)
    first_ids = {r.local_date: r.id for r in rows}
    first_values = {r.local_date: (r.run_load, r.lift_load, r.total_load, r.miles) for r in rows}

    recompute_daily_load(db, user.id, as_of=TODAY)
    rows = db.query(DailyTrainingLoad).filter(DailyTrainingLoad.user_id == user.id).all()
    assert len(rows) == 35
    assert {r.local_date: r.id for r in rows} == first_ids
    assert {r.local_date: (r.run_load, r.lift_load, r.total_load, r.miles) for r in rows} == first_values

    # Session loads were persisted.
    assert (_loaded(db, s1.id).training_load, _loaded(db, s1.id).load_estimated) == (100.0, False)
    assert (_loaded(db, s2.id).training_load, _loaded(db, s2.id).load_estimated) == (420.0, False)
    assert _row(db, user.id, TODAY).lift_load == 420.0
    assert _row(db, user.id, TODAY).miles_7d == 5.0


def test_null_local_date_row_buckets_by_fallback(db, create_test_user):
    user = _user(create_test_user)
    # Legacy watch row: no local_date, non-midnight instant → its UTC day.
    _cardio(db, user.id, TODAY, miles=3, minutes=30, stamp_local=False)
    recompute_daily_load(db, user.id, as_of=TODAY)
    assert _row(db, user.id, TODAY).run_load == 75.0


def test_miles_plan_7d_from_planned_hunts_and_ramp_high(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    monkeypatch.setattr(tls, "_progression_verdicts", lambda db_, uid, ws: [])
    campaign, arc = _campaign(db, user.id, MONDAY - timedelta(weeks=2), cadence=8)
    template = HuntTemplate(arc_id=arc.id, weekday=5, type="run", title="Long run",
                            items=[{"run": "long", "miles": "arc"}])
    db.add(template)
    db.flush()
    db.add(PlannedHunt(user_id=user.id, campaign_id=campaign.id, arc_id=arc.id,
                       template_id=template.id, date=TODAY, week_start=MONDAY,
                       week_target_miles=20.0))
    db.commit()

    for offset in (0, 2, 4):
        _cardio(db, user.id, TODAY - timedelta(days=offset), miles=9, minutes=90, zones={"z2": 5400})
    recompute_daily_load(db, user.id, as_of=TODAY)

    row = _row(db, user.id, TODAY)
    assert row.miles_plan_7d == 20.0
    assert row.miles_7d == 27.0           # > 1.20 × 20 and > 8
    assert row.longest_run_7d == 9.0      # 33% of the week: no long_run_share
    assert row.flags == [FLAG_RAMP_HIGH]
    assert guard_flags_for_date(db, user.id, TODAY) == [FLAG_RAMP_HIGH]
    # A week with no planned hunt has no plan miles.
    assert _row(db, user.id, MONDAY - timedelta(days=1)).miles_plan_7d is None


def test_miles_plan_7d_null_without_campaign(db, create_test_user):
    user = _user(create_test_user)
    _cardio(db, user.id, TODAY, miles=30, minutes=240)
    recompute_daily_load(db, user.id, as_of=TODAY)
    row = _row(db, user.id, TODAY)
    assert row.miles_plan_7d is None
    assert FLAG_RAMP_HIGH not in row.flags


def test_get_load_state_recomputes_when_a_session_lands(db, create_test_user):
    user = _user(create_test_user)
    state = get_load_state(db, user.id, TODAY)
    assert state["miles_7d"] == 0.0
    assert state["band"] == "cold_start"

    _cardio(db, user.id, TODAY, miles=4, minutes=40)
    state = get_load_state(db, user.id, TODAY)
    assert state["miles_7d"] == 4.0
    assert state["series"][-1]["local_date"] == TODAY.isoformat()
    assert state["series"][-1]["run_load"] == 100.0


# ── GET /load ───────────────────────────────────────────────────────────────

def test_get_load_endpoint_shape(client, db, auth_headers, unique_email):
    headers, user = auth_headers(email=unique_email("load"))
    _cardio(db, user.id, TODAY, miles=3, minutes=30, zones={"z2": 1800})

    resp = client.get(f"/load?client_date={TODAY.isoformat()}", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data) == {
        "as_of", "run_acute_7d", "run_chronic_28d", "run_acwr", "band",
        "miles_7d", "miles_plan_7d", "longest_run_7d", "flags", "series",
    }
    assert data["as_of"] == TODAY.isoformat()
    assert data["run_acwr"] is None
    assert data["band"] == "cold_start"
    assert data["miles_plan_7d"] is None
    assert data["miles_7d"] == 3.0
    assert data["flags"] == []
    assert len(data["series"]) == 28
    assert data["series"][0]["local_date"] == (TODAY - timedelta(days=27)).isoformat()
    for point in data["series"]:
        assert set(point) == {"local_date", "run_load", "lift_load", "total_load", "miles", "run_acwr"}
    assert data["series"][-1]["run_load"] == 60.0

    # Malformed client_date falls back to the server day rather than erroring.
    assert client.get("/load?client_date=nope", headers=headers).status_code == 200


def test_get_load_requires_auth(client):
    assert client.get("/load").status_code in (401, 403)
