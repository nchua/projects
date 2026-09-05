"""
ARISE v3 §4.6 — Objectives: v2 payloads still work, run objectives ride the
arc ramp, the preview math + AMBITIOUS, `extend_goal_deadline` bounds,
`goal_flags` (goal_behind over two weekly snapshots, goal_ambitious) and
`active_strength_goal_families`.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.goal import Goal, GoalProgressSnapshot
from app.schemas.goal import GoalCreate
from app.services.goal_service import (
    MAX_DEADLINE_EXTENSION_DAYS,
    active_strength_goal_families,
    create_goal,
    extend_goal_deadline,
    goal_flags,
    preview_goal,
    run_goal_pace,
    strength_goal_chips,
)
from tests.helpers_w1 import MONDAY, add_lift, family_exercise, import_plan, make_user


def _seed_improving_bench(db, user_id, bench, weeks=7, start=200, step=5):
    today = date.today()
    for i in range(weeks):
        day = today - timedelta(days=2 + 7 * (weeks - 1 - i))
        add_lift(db, user_id, day, [(bench, [(start + step * i, 5)])])


@pytest.fixture
def bench(db):
    return family_exercise(db, "Barbell Bench Press")


class TestCreate:
    def test_v2_payload_creates_a_strength_objective_under_the_campaign(self, client, db, auth_headers, unique_email, bench):
        headers, user = auth_headers(email=unique_email("g-v2"))
        campaign, _ = import_plan(db, user.id, date.today() - timedelta(days=date.today().weekday()))
        resp = client.post("/goals", json={
            "exercise_id": bench.id, "target_weight": 225, "target_reps": 1, "weight_unit": "lb",
            "deadline": (date.today() + timedelta(weeks=12)).isoformat(),
        }, headers=headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert (body["kind"], body["campaign_id"], body["target_miles"], body["deadline_extensions"]) == ("strength", campaign.id, None, 0)
        listed = client.get("/goals", headers=headers).json()["goals"]
        assert listed[0]["kind"] == "strength"

    def test_run_objective_by_arc_end(self, client, db, auth_headers, unique_email):
        headers, user = auth_headers(email=unique_email("g-run"))
        start = date.today() - timedelta(days=date.today().weekday())
        import_plan(db, user.id, start)
        resp = client.post("/goals", json={"kind": "run", "target_miles": 12, "run_scope": "weekly", "by": "arc_end"}, headers=headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert (body["kind"], body["target_miles"], body["run_scope"], body["exercise_id"]) == ("run", 12, "weekly", None)
        assert body["deadline"] == (start + timedelta(weeks=8) - timedelta(days=1)).isoformat()
        assert body["exercise_name"] == "Weekly miles"
        assert body["pace_status"] == "on_track"

    def test_run_objective_without_campaign_needs_a_deadline(self, client, auth_headers, unique_email):
        headers, _ = auth_headers(email=unique_email("g-run-none"))
        resp = client.post("/goals", json={"kind": "run", "target_miles": 12, "run_scope": "weekly", "by": "arc_end"}, headers=headers)
        assert resp.status_code == 400 and "no active campaign" in resp.json()["detail"]

    def test_schema_rejects_malformed_shapes(self, client, auth_headers, unique_email, bench):
        headers, _ = auth_headers(email=unique_email("g-bad"))
        assert client.post("/goals", json={"kind": "run", "target_miles": 12}, headers=headers).status_code == 422
        assert client.post("/goals", json={"exercise_id": bench.id, "deadline": "2030-01-01"}, headers=headers).status_code == 422
        assert client.post("/goals", json={"exercise_id": "nope", "target_weight": 100, "deadline": "2030-01-01"}, headers=headers).status_code == 400

    def test_active_strength_goal_families(self, db, create_test_user, bench):
        user = make_user(create_test_user, "g-fam")
        create_goal(db, user.id, bench.id, 225, "lb", date.today() + timedelta(weeks=8))
        create_goal(db, user.id, None, None, "lb", date.today() + timedelta(weeks=8), kind="run", target_miles=10, run_scope="weekly")
        db.commit()
        assert active_strength_goal_families(db, user.id) == {"bench_press"}
        assert set(strength_goal_chips(db, user.id)) == {"bench_press"}


class TestRunPace:
    def test_weekly_and_long_run_objectives_ride_the_ramp(self, db, create_test_user):
        user = make_user(create_test_user, "g-ramp")
        campaign, _ = import_plan(db, user.id, MONDAY)
        arc_end = MONDAY + timedelta(weeks=8) - timedelta(days=1)

        def probe(miles, scope):
            return Goal(user_id=user.id, kind="run", target_miles=miles, run_scope=scope,
                        deadline=arc_end, target_weight=0.0, campaign_id=campaign.id)

        assert run_goal_pace(db, probe(13, "weekly"), MONDAY)["pace_status"] == "on_track"
        assert run_goal_pace(db, probe(14, "weekly"), MONDAY)["pace_status"] == "behind"
        assert run_goal_pace(db, probe(7, "weekly"), MONDAY)["pace_status"] == "ahead"
        assert run_goal_pace(db, probe(4.5, "long_run"), MONDAY)["pace_status"] == "on_track"
        assert run_goal_pace(db, probe(5, "long_run"), MONDAY)["pace_status"] == "behind"
        pace = run_goal_pace(db, probe(13, "weekly"), MONDAY + timedelta(weeks=6))
        assert pace["ramp_now"] == pytest.approx(round(7 + 6 * 6 / 7, 1)) and pace["progress_percent"] > 90


class TestPreview:
    def test_preview_math_and_ambitious(self, db, create_test_user, bench):
        user = make_user(create_test_user, "g-prev")
        _seed_improving_bench(db, user.id, bench)           # 200 → 230 × 5, weekly; e1RM 233.3 → 268.3
        modest = GoalCreate(exercise_id=bench.id, target_weight=285, target_reps=1, deadline=date.today() + timedelta(weeks=8))
        out = preview_goal(db, user.id, modest)
        assert out["current_e1rm"] == pytest.approx(230 * (1 + 5 / 30), abs=0.1)
        assert out["target_e1rm"] == 285
        assert out["weeks_remaining"] == 8.0
        assert out["required_weekly_gain_lb"] == pytest.approx((285 - out["current_e1rm"]) / 8, abs=0.05)
        assert out["slope_6wk_lb"] == pytest.approx(5 * (1 + 5 / 30), abs=0.05)
        assert out["ambitious"] is False and out["pace_status"] == "ahead"

        wild = GoalCreate(exercise_id=bench.id, target_weight=405, target_reps=1, deadline=date.today() + timedelta(weeks=8))
        out = preview_goal(db, user.id, wild)
        assert out["required_weekly_gain_lb"] > 2 * out["slope_6wk_lb"]
        assert out["ambitious"] is True and out["pace_status"] == "behind"

    def test_preview_without_history(self, db, create_test_user, bench):
        user = make_user(create_test_user, "g-prev-none")
        out = preview_goal(db, user.id, GoalCreate(exercise_id=bench.id, target_weight=225, deadline=date.today() + timedelta(weeks=8)))
        assert (out["current_e1rm"], out["required_weekly_gain_lb"], out["slope_6wk_lb"], out["ambitious"]) == (None, None, None, False)

    def test_preview_endpoint(self, client, db, auth_headers, unique_email, bench):
        headers, user = auth_headers(email=unique_email("g-prev-api"))
        _seed_improving_bench(db, user.id, bench)
        resp = client.post("/goals/preview", json={
            "exercise_id": bench.id, "target_weight": 405, "deadline": (date.today() + timedelta(weeks=8)).isoformat(),
        }, headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ambitious"] is True and body["kind"] == "strength"
        assert set(body) >= {"current_e1rm", "target_e1rm", "required_weekly_gain_lb", "slope_6wk_lb", "weeks_remaining", "ambitious", "pace_status"}

    def test_run_preview_uses_the_ramp(self, client, db, auth_headers, unique_email):
        headers, user = auth_headers(email=unique_email("g-prev-run"))
        import_plan(db, user.id, date.today() - timedelta(days=date.today().weekday()))
        resp = client.post("/goals/preview", json={"kind": "run", "target_miles": 14, "run_scope": "weekly", "by": "arc_end"}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["pace_status"] == "behind" and resp.json()["ramp_at_deadline"] == 13.0


class TestExtendDeadline:
    def test_bounds(self, db, create_test_user, bench):
        user = make_user(create_test_user, "g-ext")
        deadline = date.today() + timedelta(weeks=8)
        goal = create_goal(db, user.id, bench.id, 225, "lb", deadline)
        db.commit()
        with pytest.raises(ValueError, match="later"):
            extend_goal_deadline(db, user.id, goal.id, deadline - timedelta(days=1))
        with pytest.raises(ValueError, match="4 weeks"):
            extend_goal_deadline(db, user.id, goal.id, deadline + timedelta(days=MAX_DEADLINE_EXTENSION_DAYS + 1))
        with pytest.raises(ValueError, match="not found"):
            extend_goal_deadline(db, user.id, "nope", deadline + timedelta(days=7))
        extended = extend_goal_deadline(db, user.id, goal.id, deadline + timedelta(days=MAX_DEADLINE_EXTENSION_DAYS))
        assert (extended.deadline, extended.deadline_extensions) == (deadline + timedelta(days=28), 1)
        with pytest.raises(ValueError, match="already"):
            extend_goal_deadline(db, user.id, goal.id, extended.deadline + timedelta(days=7))


class TestGoalFlags:
    def test_goal_behind_needs_two_weeks_behind(self, db, create_test_user, bench):
        user = make_user(create_test_user, "g-flags")
        now = datetime.now(timezone.utc)
        goal = Goal(id=str(uuid.uuid4()), user_id=user.id, exercise_id=bench.id, target_weight=300, target_reps=1,
                    weight_unit="lb", deadline=(now + timedelta(days=70)).date(), starting_e1rm=200, current_e1rm=203,
                    status="active", kind="strength")
        db.add(goal)
        db.flush()
        for days_ago, e1rm in ((35, 200), (27, 201), (14, 202), (7, 203)):
            db.add(GoalProgressSnapshot(goal_id=goal.id, recorded_at=(now - timedelta(days=days_ago)).replace(tzinfo=None), e1rm=e1rm))
        db.commit()
        flags = goal_flags(db, user.id)
        assert len(flags) == 1
        row = flags[0]
        assert (row["kind"], row["family_id"], row["pace_status"], row["goal_behind"]) == ("strength", "bench_press", "behind", True)
        assert row["required_weekly_gain"] == pytest.approx(97 / 10, abs=0.1)
        assert 0 < row["actual_weekly_gain"] < 1
        assert row["goal_ambitious"] is False                  # no weekly series → no slope → can't judge

    def test_goal_behind_false_when_only_this_week_is_behind(self, db, create_test_user, bench):
        user = make_user(create_test_user, "g-flags-1wk")
        now = datetime.now(timezone.utc)
        goal = Goal(id=str(uuid.uuid4()), user_id=user.id, exercise_id=bench.id, target_weight=260, target_reps=1,
                    weight_unit="lb", deadline=(now + timedelta(days=70)).date(), starting_e1rm=200, current_e1rm=240,
                    status="active", kind="strength")
        db.add(goal)
        db.flush()
        # fast gains until a week ago, then flat: last week on track, this week behind
        for days_ago, e1rm in ((28, 200), (21, 215), (14, 230), (8, 240), (1, 240)):
            db.add(GoalProgressSnapshot(goal_id=goal.id, recorded_at=(now - timedelta(days=days_ago)).replace(tzinfo=None), e1rm=e1rm))
        db.commit()
        row = goal_flags(db, user.id)[0]
        assert row["goal_behind"] is False

    def test_goal_ambitious_from_the_six_week_slope(self, db, create_test_user, bench):
        user = make_user(create_test_user, "g-amb")
        _seed_improving_bench(db, user.id, bench)
        create_goal(db, user.id, bench.id, 405, "lb", date.today() + timedelta(weeks=8))
        create_goal(db, user.id, None, None, "lb", date.today() + timedelta(weeks=8), kind="run", target_miles=10, run_scope="weekly")
        db.commit()
        rows = {r["kind"]: r for r in goal_flags(db, user.id)}
        assert rows["strength"]["goal_ambitious"] is True
        assert rows["strength"]["slope_6wk_lb"] == pytest.approx(5 * (1 + 5 / 30), abs=0.05)
        assert rows["run"]["goal_ambitious"] is False and rows["run"]["target_miles"] == 10
