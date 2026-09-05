"""
Debrief engine step (ARISE v3 §8.4): adherence, highlights, every concern
trigger, every candidate op with its numbers, and the fallback summary.
"""
from datetime import datetime, timedelta

import pytest

from app.models.campaign import PlannedHuntStatus
from app.models.gate import GateStatus, PRGate
from app.services.debrief_service import (
    MAX_CANDIDATES,
    build_candidates,
    describe_op,
    engine_summary,
)
from tests.helpers_coach import (
    install_fake_w1,
    install_fake_w2,
    seed_four_weeks,
    sentence_count,
)

STALL = {
    "family_id": "bench_press", "display_name": "Bench Press", "verdict": "deload_lift",
    "last_weight_lb": 195.0, "next_weight_lb": 195.0, "increment_lb": 5.0,
    "sets_hit": 3, "sets_total": 5, "reason": "two consecutive holds",
}
BEHIND = {
    "goal_id": None, "kind": "strength", "family_id": "bench_press", "exercise_id": None,
    "target_weight": 225.0, "target_reps": 1, "deadline": None, "pace_status": "behind",
    "goal_behind": True, "goal_ambitious": False, "required_weekly_gain": 1.9, "actual_weekly_gain": 0.4,
}


@pytest.fixture
def athlete(db, create_test_user, unique_email):
    user, _ = create_test_user(email=unique_email("engine"))
    return seed_four_weeks(db, user)


def _ops(candidates, op):
    return [c for c in candidates["candidate_ops"] if c["op"] == op]


def _flags(candidates):
    return [c["flag"] for c in candidates["concerns"]]


def test_adherence_counts_by_status(db, athlete, monkeypatch):
    install_fake_w1(monkeypatch)
    install_fake_w2(monkeypatch)
    sunday = athlete.week_start + timedelta(days=6)
    tuesday = athlete.week_start + timedelta(days=1)
    athlete.hunts[sunday].status = PlannedHuntStatus.MOVED.value
    athlete.hunts[sunday].moved_to = athlete.next_week
    athlete.hunts[tuesday].status = PlannedHuntStatus.SKIPPED.value
    db.commit()
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    assert c["adherence"] == {"planned": 5, "done": 3, "modified": 0, "moved": 1, "skipped": 1}
    kinds = [h["kind"] for h in c["highlights"]]
    assert "week_completed_as_planned" not in kinds and "four_weeks_on_plan" not in kinds


def test_clean_week_highlights(db, athlete, monkeypatch):
    install_fake_w1(monkeypatch)
    install_fake_w2(monkeypatch)
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    assert c["adherence"]["planned"] == 5 and c["adherence"]["done"] == 5
    by_kind = {h["kind"]: h for h in c["highlights"]}
    assert by_kind["pr"]["text"] == "Barbell Back Squat 240×5 → e1RM 280 (+5.8)"
    assert by_kind["pr"]["numbers"] == {"e1rm": 280.0, "delta": 5.8}
    assert by_kind["week_completed_as_planned"]["text"] == "Week completed as planned: 5/5 hunts."
    assert by_kind["longest_run"]["numbers"]["miles"] == pytest.approx(4.95, abs=0.01)
    assert by_kind["four_weeks_on_plan"]["numbers"] == {"weeks": 4}
    assert c["concerns"] == [] and c["candidate_ops"] == []


def test_gate_clear_highlight(db, athlete, monkeypatch):
    install_fake_w1(monkeypatch)
    install_fake_w2(monkeypatch)
    saturday = datetime.combine(athlete.week_start + timedelta(days=5), datetime.min.time())
    db.add(PRGate(
        user_id=athlete.user.id, exercise_id=athlete.squat.id, family_id="back_squat",
        rank="B", name="B-Rank Gate: Squat 240×5", target_weight=240, target_reps=5,
        target_e1rm=280, baseline_e1rm=262.5, projected_e1rm=281, weekly_slope=4.2,
        condition_at_spawn=78, status=GateStatus.CLEARED.value,
        spawned_at=saturday - timedelta(days=10), expires_at=saturday + timedelta(days=4),
        cleared_at=saturday + timedelta(hours=10), xp_awarded=500,
    ))
    db.commit()
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    gate = next(h for h in c["highlights"] if h["kind"] == "gate_cleared")
    assert gate["text"] == "B-Rank Gate: Squat 240×5 cleared (+500 XP)"


@pytest.mark.parametrize("flag,text_fragment", [
    ("ramp_high", "Ran 12.5 mi against 11.0 planned (+14%)."),
    ("long_run_share", "Longest run 6.0 mi is 48% of the week's 12.5 mi."),
    ("run_acwr_high", "Run ACWR 1.35 (limit 1.30)."),
    ("run_acwr_critical", "Run ACWR 1.35 (critical above 1.50)."),
    ("deload_due", "Deload due: the arc's cadence."),
])
def test_guard_flag_concerns_carry_numbers(db, athlete, monkeypatch, flag, text_fragment):
    install_fake_w1(monkeypatch)
    install_fake_w2(monkeypatch, flags=(flag,), miles_7d=12.5, miles_plan_7d=11.0, run_acwr=1.35, longest_run_7d=6.0)
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    concern = next(x for x in c["concerns"] if x["flag"] == flag)
    assert concern["text"] == text_fragment
    assert concern["numbers"]


def test_critical_acwr_suppresses_high(db, athlete, monkeypatch):
    install_fake_w1(monkeypatch)
    install_fake_w2(monkeypatch, flags=("run_acwr_high", "run_acwr_critical"), run_acwr=1.62)
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    assert _flags(c) == ["run_acwr_critical"]
    miles = _ops(c, "set_week_miles")[0]
    assert miles["miles"] == pytest.approx(9.6)   # 12 × 0.8
    assert miles["numbers"]["run_acwr"] == 1.62


def test_lift_stall_from_verdicts_proposes_deload(db, athlete, monkeypatch):
    install_fake_w1(monkeypatch, verdicts=[STALL])
    install_fake_w2(monkeypatch)
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    stall = next(x for x in c["concerns"] if x["flag"] == "lift_stall")
    assert stall["text"] == "Bench Press: two consecutive holds — held at 195 lb."
    assert stall["numbers"]["family_id"] == "bench_press"
    deload = _ops(c, "deload_now")[0]
    assert deload["scope"] == "lifts" and deload["source"] == "engine"
    assert _ops(c, "set_progression") == []


def test_recent_deload_turns_stall_into_set_progression(db, athlete, monkeypatch):
    athlete.campaign.overrides = {"last_deload_week": (athlete.next_week - timedelta(days=7)).isoformat()}
    db.commit()
    install_fake_w1(monkeypatch, verdicts=[STALL])
    install_fake_w2(monkeypatch, flags=("deload_due",))
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    assert _ops(c, "deload_now") == []
    prog = _ops(c, "set_progression")[0]
    assert prog["family"] == "bench_press" and prog["increment_lb"] == 5.0
    assert prog["numbers"]["last_weight_lb"] == 195.0


def test_deload_due_proposes_deload_and_reduced_miles(db, athlete, monkeypatch):
    install_fake_w1(monkeypatch, verdicts=[STALL, dict(STALL, family_id="back_squat", display_name="Back Squat")])
    install_fake_w2(monkeypatch, flags=("deload_due",))
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    due = next(x for x in c["concerns"] if x["flag"] == "deload_due")
    assert due["text"] == "Deload due: two lifts stalled this week."
    deload = _ops(c, "deload_now")
    assert len(deload) == 1 and deload[0]["scope"] == "all" and deload[0]["confidence"] == "high"
    miles = _ops(c, "set_week_miles")[0]
    assert miles["week_start"] == athlete.next_week.isoformat()
    assert miles["miles"] == pytest.approx(9.0)    # 12 × arc deload_factor 0.75
    assert miles["numbers"]["plan_next_week"] == 12.0


def test_ramp_high_holds_next_week_at_plan(db, athlete, monkeypatch):
    install_fake_w1(monkeypatch)
    install_fake_w2(monkeypatch, flags=("ramp_high",), miles_7d=13.2, miles_plan_7d=11.0)
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    miles = _ops(c, "set_week_miles")[0]
    assert miles["miles"] == 11.0
    assert miles["numbers"] == {"plan_next_week": 12.0, "miles_7d": 13.2, "miles_plan_7d": 11.0, "run_acwr": 1.05}


def test_sleep_low_and_condition_low(db, create_test_user, unique_email, monkeypatch):
    user, _ = create_test_user(email=unique_email("sleep"))
    s = seed_four_weeks(db, user, low_sleep_nights=3)
    install_fake_w1(monkeypatch)
    install_fake_w2(monkeypatch)
    c = build_candidates(db, user.id, s.week_start)
    sleep = next(x for x in c["concerns"] if x["flag"] == "sleep_low")
    assert sleep["text"] == "Sleep under 6 h on 3 nights (avg 5.5 h)."
    cond = next(x for x in c["concerns"] if x["flag"] == "condition_low")
    assert cond["numbers"]["days"] == 3 and cond["numbers"]["min"] < 65


def test_goal_behind_unlocks_change_reps_and_deadline(db, athlete, monkeypatch):
    flag = dict(BEHIND, goal_id=athlete.goal.id)
    install_fake_w1(monkeypatch, goal_flags=[flag, dict(flag, goal_behind=False, goal_ambitious=True)])
    install_fake_w2(monkeypatch)
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    assert "goal_behind" in _flags(c) and "goal_ambitious" in _flags(c)
    behind = next(x for x in c["concerns"] if x["flag"] == "goal_behind")
    assert behind["text"] == "bench_press objective behind: needs +1.9 lb/wk, actual +0.4."
    reps = _ops(c, "change_reps")[0]
    assert reps["family"] == "bench_press" and reps["sets"] == 3 and reps["reps"] == [3, 3]
    deadline = _ops(c, "set_goal_deadline")[0]
    assert deadline["goal_id"] == athlete.goal.id
    assert deadline["deadline"] == (athlete.goal.deadline + timedelta(days=28)).isoformat()
    assert deadline["numbers"]["deadline_extensions"] == 0


def test_goal_already_extended_skips_deadline_op(db, athlete, monkeypatch):
    athlete.goal.deadline_extensions = 1
    db.commit()
    install_fake_w1(monkeypatch, goal_flags=[dict(BEHIND, goal_id=athlete.goal.id)])
    install_fake_w2(monkeypatch)
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    assert _ops(c, "set_goal_deadline") == []
    assert len(_ops(c, "change_reps")) == 1


def test_plan_drift_and_repeated_move_pattern(db, athlete, monkeypatch):
    install_fake_w1(monkeypatch)
    install_fake_w2(monkeypatch)
    for monday in athlete.weeks[-2:]:
        saturday = monday + timedelta(days=5)
        athlete.hunts[saturday].status = PlannedHuntStatus.MOVED.value
        athlete.hunts[saturday].moved_to = saturday + timedelta(days=1)
    thursday = athlete.week_start + timedelta(days=3)
    athlete.hunts[thursday].status = PlannedHuntStatus.MOVED.value
    athlete.hunts[thursday].moved_to = thursday + timedelta(days=1)
    db.commit()
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    assert c["adherence"]["moved"] == 2
    drift = next(x for x in c["concerns"] if x["flag"] == "plan_drift")
    assert drift["numbers"] == {"moved": 2}
    swap = _ops(c, "swap_days")[0]
    assert swap["a"] == (athlete.next_week + timedelta(days=5)).isoformat()
    assert swap["b"] == (athlete.next_week + timedelta(days=6)).isoformat()
    assert swap["confidence"] == "low"


def test_never_more_than_six_candidates(db, athlete, monkeypatch):
    flag = dict(BEHIND, goal_id=athlete.goal.id)
    install_fake_w1(
        monkeypatch,
        verdicts=[STALL, dict(STALL, family_id="back_squat", display_name="Back Squat")],
        goal_flags=[flag, dict(flag, family_id="back_squat"), dict(flag, family_id="back_squat")],
    )
    install_fake_w2(monkeypatch, flags=("deload_due", "ramp_high"), miles_7d=13.0, miles_plan_7d=11.0)
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    assert len(c["candidate_ops"]) == MAX_CANDIDATES
    assert all(op["source"] == "engine" and op["numbers"] for op in c["candidate_ops"])
    assert "extend_arc" not in {op["op"] for op in c["candidate_ops"]}


def test_engine_summary_is_at_most_three_sentences(db, athlete, monkeypatch):
    install_fake_w1(monkeypatch, verdicts=[STALL])
    install_fake_w2(monkeypatch, flags=("ramp_high",), miles_7d=12.5, miles_plan_7d=11.0)
    c = build_candidates(db, athlete.user.id, athlete.week_start)
    text = engine_summary(c)
    assert sentence_count(text) <= 3
    assert text.startswith("5 of 5 hunts done.")
    assert "Top concern: Ran 12.5 mi against 11.0 planned (+14%)." in text
    assert text.endswith(f"Proposed: {describe_op(c['candidate_ops'][0])}.")

    empty = engine_summary({"adherence": {"planned": 0}, "concerns": [], "candidate_ops": []})
    assert empty == "No planned hunts this week. No flags raised. No adjustment proposed; the plan stands."
