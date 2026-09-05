"""
Tests for Gates v2 (ARISE v3 spec §10, §4.6 item 1).

Spawn with exactly four weekly points (three is too few); the campaign-best
baseline vs the 12-week fallback; family grouping (a Saturday back squat and
a Sunday "Squat" alias are one weekly point and one gate); spawning onto the
next planned hunt with a hunt + 7-day window; the objective tie-break;
``gate_for_planned_hunt``; ``gate_cleared`` on the create response; and the
rule that warm-up sets never clear a gate.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

from app.models.campaign import Campaign, CampaignArc, HuntTemplate, PlannedHunt
from app.models.exercise import Exercise
from app.models.gate import GateStatus
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.services import gate_service
from app.services.exercise_family_defs import family_for_name
from app.services.exercise_family_service import families_for_user
from app.services.gate_service import (
    check_gate_clear,
    evaluate_gate_spawns,
    gate_for_planned_hunt,
)
from app.services.trend_service import weekly_best_e1rm_series

# ── Helpers ─────────────────────────────────────────────────────────────────

def _user(create_test_user):
    return create_test_user(email=f"gate2-{uuid.uuid4().hex[:8]}@example.com")[0]


def _exercise(db, name, primary="Chest"):
    ex = Exercise(id=str(uuid.uuid4()), name=name, family_id=family_for_name(name),
                  category="compound", primary_muscle=primary, secondary_muscles=[],
                  is_custom=False, user_id=None)
    db.add(ex)
    db.commit()
    assert ex.family_id is not None, f"{name} must resolve to a family"
    return ex


def _workout(db, user_id, exercise, when, sets=((135, 8),), warmup=False):
    workout = WorkoutSession(user_id=user_id, date=when, local_date=when.date(), duration_minutes=45)
    db.add(workout)
    db.flush()
    we = WorkoutExercise(session_id=workout.id, exercise_id=exercise.id, order_index=0)
    db.add(we)
    db.flush()
    rows = []
    for n, (weight, reps) in enumerate(sets, start=1):
        s = Set(workout_exercise_id=we.id, weight=weight, weight_lb=weight, reps=reps,
                set_number=n, is_warmup=warmup, e1rm=round(weight * (1 + reps / 30), 2))
        db.add(s)
        rows.append(s)
    db.commit()
    return workout, we, rows


def _seed_weeks(db, user_id, exercise, weeks, start_weight=225, step=5, reps=5, exercises=None):
    """One improving workout per week, newest 2 days ago. ``exercises`` may
    alternate a list of exercises week by week (family grouping tests)."""
    today = date.today()
    for i in range(weeks):
        days_ago = 2 + 7 * (weeks - 1 - i)
        when = datetime.combine(today - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=10)
        ex = exercises[i % len(exercises)] if exercises else exercise
        _workout(db, user_id, ex, when, sets=((start_weight + step * i, reps),))


def _patch_condition(monkeypatch, score=80):
    from app.services.condition_service import band_for_score

    def _fake(db, user_id, client_date=None, user_age=None):
        return {"score": score, "band": band_for_score(score),
                "generated_at": "", "inputs": [], "muscles_cooling": []}

    monkeypatch.setattr(gate_service, "compute_condition", _fake)


def _campaign(db, user_id, start, *, items=None, hunt_date=None, week_target_miles=None):
    campaign = Campaign(user_id=user_id, name="Base", start_date=start)
    db.add(campaign)
    db.flush()
    arc = CampaignArc(campaign_id=campaign.id, index=0, name="Arc", weeks=12)
    db.add(arc)
    db.flush()
    template = HuntTemplate(arc_id=arc.id, weekday=5, type="lift", title="Lower",
                            items=items or [])
    db.add(template)
    db.flush()
    hunt = None
    if hunt_date is not None:
        hunt = PlannedHunt(user_id=user_id, campaign_id=campaign.id, arc_id=arc.id,
                           template_id=template.id, date=hunt_date,
                           week_start=hunt_date - timedelta(days=hunt_date.weekday()),
                           week_target_miles=week_target_miles)
        db.add(hunt)
    db.commit()
    return campaign, template, hunt


# ── §10.2: four weekly points ───────────────────────────────────────────────

def test_spawn_with_exactly_four_weekly_points(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    bench = _exercise(db, "Barbell Bench Press")
    _seed_weeks(db, user.id, bench, weeks=4)
    _patch_condition(monkeypatch)

    spawned = evaluate_gate_spawns(db, user.id)
    assert len(spawned) == 1
    gate = spawned[0]
    assert gate.family_id == "bench_press"
    assert gate.exercise_id == bench.id
    assert gate.planned_hunt_id is None
    assert (gate.expires_at - gate.spawned_at).days == 14
    assert gate.name.startswith(f"{gate.rank}-Rank Gate: Bench ")


def test_no_spawn_with_three_weekly_points(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    bench = _exercise(db, "Barbell Bench Press")
    _seed_weeks(db, user.id, bench, weeks=3)
    _patch_condition(monkeypatch)
    assert evaluate_gate_spawns(db, user.id) == []


# ── §10.1: campaign-best baseline ───────────────────────────────────────────

def test_campaign_best_baseline_ignores_pre_campaign_single(db, create_test_user, monkeypatch):
    """An old heavy single (lifetime PR) inside the 12-week fallback blocks a
    5×5 trajectory; once a Campaign starts after it, the baseline is the
    campaign best and the gate spawns."""
    user = _user(create_test_user)
    squat = _exercise(db, "Barbell Back Squat", primary="Quads")
    today = date.today()
    # A 315×1 single 10 weeks ago (e1RM 325.5) …
    when = datetime.combine(today - timedelta(weeks=10), datetime.min.time()) + timedelta(hours=10)
    _workout(db, user.id, squat, when, sets=((315, 1),))
    # … then six weeks of 5×5 climbing 225 → 250 (e1RM 262.5 → 291.7).
    _seed_weeks(db, user.id, squat, weeks=6, start_weight=225, step=5)
    _patch_condition(monkeypatch)

    # No campaign: baseline = last 12 weeks → the single wins → no gate.
    assert evaluate_gate_spawns(db, user.id) == []

    # Campaign started 7 weeks ago (after the single): baseline = campaign best.
    _campaign(db, user.id, today - timedelta(weeks=7))
    spawned = evaluate_gate_spawns(db, user.id)
    assert len(spawned) == 1
    assert spawned[0].baseline_e1rm == round(250 * (1 + 5 / 30), 2)
    assert spawned[0].target_e1rm > spawned[0].baseline_e1rm


# ── §10.2: family grouping ──────────────────────────────────────────────────

def test_family_groups_alias_into_one_weekly_point_and_one_gate(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    back_squat = _exercise(db, "Barbell Back Squat", primary="Quads")
    alias = _exercise(db, "Squat", primary="Quads")
    assert back_squat.family_id == alias.family_id == "back_squat"

    # Saturday back squat + Sunday "Squat" in the same week → one point.
    monday = date.today() - timedelta(days=date.today().weekday()) - timedelta(weeks=1)
    sat = datetime.combine(monday + timedelta(days=5), datetime.min.time()) + timedelta(hours=10)
    sun = datetime.combine(monday + timedelta(days=6), datetime.min.time()) + timedelta(hours=10)
    _workout(db, user.id, back_squat, sat, sets=((225, 5),))
    _workout(db, user.id, alias, sun, sets=((235, 5),))

    fams = {f["family_id"]: f for f in families_for_user(db, user.id)}
    assert set(fams["back_squat"]["exercise_ids"]) == {back_squat.id, alias.id}
    series = weekly_best_e1rm_series(db, user.id, fams["back_squat"]["exercise_ids"])
    assert len(series) == 1
    assert series[0] == (monday, round(235 * (1 + 5 / 30), 2))

    # Alternating the two exercises week by week still yields one gate.
    _seed_weeks(db, user.id, None, weeks=4, start_weight=240, exercises=[back_squat, alias])
    _patch_condition(monkeypatch)
    spawned = evaluate_gate_spawns(db, user.id)
    assert len(spawned) == 1
    assert spawned[0].family_id == "back_squat"
    assert spawned[0].name.startswith(f"{spawned[0].rank}-Rank Gate: Squat ")
    # No second gate for the alias: the family is taken.
    assert evaluate_gate_spawns(db, user.id) == []


# ── §10.3: spawn onto the plan ──────────────────────────────────────────────

def test_spawn_targets_next_planned_hunt_with_hunt_plus_7_window(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    bench = _exercise(db, "Barbell Bench Press")
    _seed_weeks(db, user.id, bench, weeks=6)
    today = date.today()
    _, _, hunt = _campaign(
        db, user.id, today - timedelta(weeks=4),
        items=[{"family": "bench_press", "sets": 5, "reps": [5, 5], "role": "main"}],
        hunt_date=today + timedelta(days=3),
    )
    captured = {}

    def fake_next(db_, user_id, family_id, after):
        captured["args"] = (user_id, family_id, after)
        return hunt if family_id == "bench_press" else None

    monkeypatch.setattr(gate_service, "_next_planned_hunt_with_family", fake_next)
    _patch_condition(monkeypatch)

    spawned = evaluate_gate_spawns(db, user.id, client_date=today)
    assert len(spawned) == 1
    gate = spawned[0]
    assert captured["args"] == (user.id, "bench_press", today)
    assert gate.planned_hunt_id == hunt.id
    assert gate.expires_at.date() == hunt.date + timedelta(days=7)
    assert gate.expires_at.hour == 23
    # And the hunt resolves back to its gate.
    assert gate_for_planned_hunt(db, user.id, hunt).id == gate.id


# ── §4.6 item 1: objective tie-break ────────────────────────────────────────

def test_objective_wins_the_slot(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    squat = _exercise(db, "Barbell Back Squat", primary="Quads")
    bench = _exercise(db, "Barbell Bench Press")
    _seed_weeks(db, user.id, squat, weeks=6, start_weight=225)
    _seed_weeks(db, user.id, bench, weeks=6, start_weight=185)
    _patch_condition(monkeypatch)
    monkeypatch.setattr(gate_service, "MAX_OPEN_GATES_TOTAL", 1)

    # Alphabetically "Back Squat" sorts first; the bench objective must win.
    monkeypatch.setattr(gate_service, "_active_strength_goal_families",
                        lambda db_, uid: {"bench_press"})
    spawned = evaluate_gate_spawns(db, user.id)
    assert [g.family_id for g in spawned] == ["bench_press"]


def test_without_objectives_both_lifts_can_spawn(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    squat = _exercise(db, "Barbell Back Squat", primary="Quads")
    bench = _exercise(db, "Barbell Bench Press")
    _seed_weeks(db, user.id, squat, weeks=6, start_weight=225)
    _seed_weeks(db, user.id, bench, weeks=6, start_weight=185)
    _patch_condition(monkeypatch)
    spawned = evaluate_gate_spawns(db, user.id)
    assert {g.family_id for g in spawned} == {"back_squat", "bench_press"}


# ── gate_for_planned_hunt ───────────────────────────────────────────────────

def test_gate_for_planned_hunt_matches_family_and_window(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    bench = _exercise(db, "Barbell Bench Press")
    _seed_weeks(db, user.id, bench, weeks=6)
    _patch_condition(monkeypatch)
    gate = evaluate_gate_spawns(db, user.id)[0]
    today = date.today()

    campaign, template, hunt = _campaign(
        db, user.id, today - timedelta(weeks=2),
        items=[{"family": "bench_press", "sets": 5, "reps": [5, 5], "role": "main"}],
        hunt_date=today + timedelta(days=2),
    )
    assert gate_for_planned_hunt(db, user.id, hunt).id == gate.id

    # Same family but outside the window → None.
    hunt.date = today + timedelta(days=30)
    db.commit()
    assert gate_for_planned_hunt(db, user.id, hunt) is None

    # Inside the window but the hunt doesn't contain the family → None.
    hunt.date = today + timedelta(days=2)
    template.items = [{"family": "deadlift", "sets": 3, "reps": [5, 5], "role": "main"}]
    db.commit()
    assert gate_for_planned_hunt(db, user.id, hunt) is None

    # Accessory role doesn't count; the stored prescription is the fallback.
    template.items = [{"family": "bench_press", "sets": 3, "reps": [8, 10], "role": "accessory"}]
    db.commit()
    assert gate_for_planned_hunt(db, user.id, hunt) is None
    template.items = []
    hunt.prescription = {"version": 1, "exercises": [
        {"family_id": "bench_press", "exercise_id": bench.id, "role": "secondary", "sets": []},
    ]}
    db.commit()
    assert gate_for_planned_hunt(db, user.id, hunt).id == gate.id


# ── §10.5: gate_cleared on the create response ──────────────────────────────

def test_gate_cleared_in_create_response(client, db, auth_headers, unique_email, monkeypatch):
    headers, user = auth_headers(email=unique_email("gate2"))
    bench = _exercise(db, "Barbell Bench Press")
    _seed_weeks(db, user.id, bench, weeks=6)
    _patch_condition(monkeypatch)
    gate = evaluate_gate_spawns(db, user.id)[0]

    def _post(weight, reps, **set_extra):
        body = {
            "date": date.today().isoformat(),
            "exercises": [{"exercise_id": bench.id, "order_index": 0, "sets": [
                {"weight": weight, "reps": reps, "set_number": 1, **set_extra},
            ]}],
        }
        return client.post("/workouts", json=body, headers=headers)

    # A sub-target workout carries no celebration.
    resp = _post(95, 5)
    assert resp.status_code == 201, resp.text
    assert resp.json()["gate_cleared"] is None

    # Beating the target clears it and the payload is the small celebration.
    resp = _post(gate.target_weight + 10, gate.target_reps)
    assert resp.status_code == 201, resp.text
    cleared = resp.json()["gate_cleared"]
    assert cleared == {
        "gate_id": gate.id,
        "name": gate.name,
        "rank": gate.rank,
        "xp_awarded": gate.xp_awarded,
        "target_weight": gate.target_weight,
        "target_reps": gate.target_reps,
    }
    assert cleared["xp_awarded"] > 0
    db.refresh(gate)
    assert gate.status == GateStatus.CLEARED.value


def test_warmups_never_clear_a_gate(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    bench = _exercise(db, "Barbell Bench Press")
    _seed_weeks(db, user.id, bench, weeks=6)
    _patch_condition(monkeypatch)
    gate = evaluate_gate_spawns(db, user.id)[0]

    when = datetime.now(timezone.utc).replace(tzinfo=None)
    _, we, sets = _workout(db, user.id, bench, when,
                           sets=((gate.target_weight + 20, gate.target_reps),), warmup=True)
    assert check_gate_clear(db, user.id, we, sets) == []
    assert gate.status == GateStatus.OPEN.value

    # The same set as a working set clears it.
    _, we2, sets2 = _workout(db, user.id, bench, when,
                             sets=((gate.target_weight + 20, gate.target_reps),))
    cleared = check_gate_clear(db, user.id, we2, sets2)
    assert len(cleared) == 1 and cleared[0]["gate"].id == gate.id
