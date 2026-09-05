"""
ARISE v3 §5 / §6.4 / §10 — the prescription engine: every verdict row,
anchors (last session, e1RM-derived ignoring high-rep sets, none),
rounding, overrides, readiness modulation per band, guard action per flag,
gate-as-set-1 with −10% back-offs and the STRAINED deferral, the System
line, `progression_verdicts`, the `/hunts` endpoints end to end and
`GET /exercises/{id}/last-performance`.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.campaign import PlannedHunt, PlannedHuntStatus
from app.models.gate import GateStatus, PRGate
from app.models.training_load import DailyTrainingLoad
from app.models.user import UserProfile, WeightUnit
from app.models.workout import Set
from app.services import campaign_service
from app.services.campaign_service import materialize_range
from app.services.prescription_service import (
    FIRST_SESSION_TEXT,
    FamilySession,
    decide_verdict,
    hr_cap_bpm,
    pct_for_reps,
    prescribe,
    progression_verdicts,
    round_to_increment,
    working_sets,
)
from tests.helpers_w1 import (
    MONDAY,
    add_lift,
    add_run,
    condition,
    fake_condition,
    family_exercise,
    hunt_for,
    import_plan,
    load_phases,
    make_user,
    sat,
    sun,
    weekday,
)

SQUAT_ITEM = {"family": "back_squat", "sets": 5, "reps": [5, 5], "role": "main",
              "progression": "linear", "increment_lb": 5.0, "rpe_cap": 8}
DOUBLE_ITEM = {"family": "leg_press", "sets": 3, "reps": [10, 12], "role": "accessory",
               "progression": "double", "increment_lb": 5.0, "rpe_cap": 9}


def _sets(weight, reps_list, rpe=None):
    return [Set(weight=weight, weight_lb=weight, reps=r, rpe=rpe, set_number=i + 1, is_warmup=False)
            for i, r in enumerate(reps_list)]


def _fs(weight, reps_list, rpe=None, day=None):
    return FamilySession(session=None, local_day=day or date(2026, 8, 29), sets=_sets(weight, reps_list, rpe))


class TestHelpers:
    def test_round_to_increment(self):
        assert round_to_increment(202.5, 5) == 200.0          # banker's rounding at the midpoint
        assert round_to_increment(233, 5) == 235.0
        assert round_to_increment(36.4, 2.5) == 37.5
        assert round_to_increment(None, 5) is None
        # kg: 230 lb → 104.3 kg → 105 kg (2.5 kg steps) → 231.5 lb, stored in lb
        assert round_to_increment(230, 5, unit="kg") == 231.5
        assert round_to_increment(60, 2.5, unit="kg") == pytest.approx(27.5 * 2.20462, abs=0.05)

    def test_pct_for_reps_is_epley_inverse(self):
        assert pct_for_reps(5) == pytest.approx(1 / (1 + 5 / 30))
        assert pct_for_reps(5) * 262.5 == pytest.approx(225.0)     # 225×5 → e1RM 262.5 → back to 225

    def test_hr_cap(self):
        assert hr_cap_bpm(None, None) == 133
        assert hr_cap_bpm(40, None) == 126
        assert hr_cap_bpm(40, 150) == 150

    def test_working_sets_picks_modal_weight_ties_heaviest(self):
        sets = _sets(225, [5, 5, 5]) + _sets(185, [8, 8, 8])
        assert working_sets(sets)[0] == 225.0
        sets = _sets(225, [5, 5]) + _sets(185, [8, 8, 8])
        assert working_sets(sets)[0] == 185.0
        warm = Set(weight=135, weight_lb=135, reps=5, set_number=0, is_warmup=True)
        weight, chosen = working_sets([warm] + _sets(225, [5]))
        assert weight == 225.0 and len(chosen) == 1 and not chosen[0].is_warmup
        assert working_sets([warm]) == (None, [])


class TestVerdicts:
    def test_linear_all_hit_progresses(self):
        v = decide_verdict(SQUAT_ITEM, _fs(225, [5, 5, 5, 5, 5]), None, 5.0)
        assert (v.verdict, v.next_weight_lb, v.sets_hit, v.sets_total) == ("progress", 230.0, 5, 5)

    def test_linear_rpe_at_cap_plus_two_holds(self):
        v = decide_verdict(SQUAT_ITEM, _fs(225, [5, 5, 5, 5, 5], rpe=10), None, 5.0)
        assert (v.verdict, v.next_weight_lb) == ("hold", 225.0)
        assert "RPE 10" in v.reason

    def test_linear_rpe_nine_still_progresses(self):
        v = decide_verdict(SQUAT_ITEM, _fs(225, [5, 5, 5, 5, 5], rpe=9), None, 5.0)
        assert v.verdict == "progress"

    def test_linear_short_by_one_holds(self):
        v = decide_verdict(SQUAT_ITEM, _fs(225, [5, 5, 5, 5, 4]), None, 5.0)
        assert (v.verdict, v.next_weight_lb, v.sets_hit) == ("hold", 225.0, 4)
        assert "1 rep short" in v.reason

    def test_linear_big_miss_once_holds(self):
        v = decide_verdict(SQUAT_ITEM, _fs(225, [5, 3, 3, 2, 2]), _fs(225, [5, 5, 5, 5, 5]), 5.0)
        assert v.verdict == "hold"

    def test_linear_big_miss_twice_deloads_ten_percent(self):
        v = decide_verdict(SQUAT_ITEM, _fs(225, [5, 3, 3, 2, 2]), _fs(225, [4, 3, 3, 3, 3]), 5.0)
        assert (v.verdict, v.next_weight_lb) == ("deload_lift", 200.0)

    def test_double_all_at_hi_progresses_and_resets_reps(self):
        v = decide_verdict(DOUBLE_ITEM, _fs(360, [12, 12, 12]), None, 5.0)
        assert (v.verdict, v.next_weight_lb, v.target_reps) == ("progress", 365.0, (10, 12))

    def test_double_else_holds_and_bumps_target(self):
        v = decide_verdict(DOUBLE_ITEM, _fs(360, [12, 11, 10]), None, 5.0)
        assert (v.verdict, v.next_weight_lb, v.target_reps) == ("hold", 360.0, (11, 12))
        v = decide_verdict(DOUBLE_ITEM, _fs(360, [12, 12, 11]), None, 5.0)
        assert v.target_reps == (12, 12)

    def test_no_working_sets_is_first(self):
        v = decide_verdict(SQUAT_ITEM, FamilySession(None, date(2026, 8, 29), []), None, 5.0)
        assert v.verdict == "first" and v.reason == FIRST_SESSION_TEXT


@pytest.fixture
def squat(db):
    return family_exercise(db, "Barbell Back Squat")


@pytest.fixture
def deadlift(db):
    return family_exercise(db, "Barbell Deadlift")


@pytest.fixture
def campaign_user(db, create_test_user):
    user = make_user(create_test_user, "rx")
    campaign, _ = import_plan(db, user.id)
    materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=13), today=MONDAY)
    db.commit()
    return user, campaign


def _rx(db, user_id, day, **kw):
    hunt = hunt_for(db, user_id, day)
    return prescribe(db, hunt, **kw)


def _main(p, family="back_squat"):
    return next(e for e in p.exercises if e["family_id"] == family)


def _work(ex):
    return [s for s in ex["sets"] if not s["is_warmup"]]


class TestAnchors:
    def test_no_anchor_prescribes_null_weight(self, db, campaign_user):
        user, _ = campaign_user
        p = _rx(db, user.id, sat())
        sq = _main(p)
        assert all(s["target_weight_lb"] is None for s in sq["sets"])
        assert len(sq["sets"]) == 5                                    # no warm-ups without a weight
        assert any(ln["key"] == "anchor:back_squat" and FIRST_SESSION_TEXT in ln["text"] for ln in p.rationale)
        assert p.system_line.startswith("[FIRST]")

    def test_last_session_anchor_with_warmups(self, db, campaign_user, squat, deadlift):
        user, _ = campaign_user
        add_lift(db, user.id, sat(), [(squat, [(135, 5, None, True)] + [(225, 5)] * 5), (deadlift, [(315, 5)] * 3 + [(315, 4)])])
        p = _rx(db, user.id, sat(1))
        sq = _main(p)
        warm = [s for s in sq["sets"] if s["is_warmup"]]
        assert [(s["target_weight_lb"], s["target_reps_lo"]) for s in warm] == [(90.0, 5), (140.0, 3), (185.0, 2)]
        assert [s["target_weight_lb"] for s in _work(sq)] == [230.0] * 5
        assert [s["set_number"] for s in _work(sq)] == [1, 2, 3, 4, 5]
        assert sq["last_performance"] == "225×5×5"
        assert sq["exercise_id"] == squat.id
        dl = _main(p, "deadlift")
        assert [s["target_weight_lb"] for s in dl["sets"]] == [315.0] * 4       # secondary: no warm-ups
        assert "HOLD" in dl["progression_note"]
        assert p.system_line == "[+5] LAST 225×5×5"

    def test_anchor_window_is_21_days(self, db, campaign_user, squat):
        user, _ = campaign_user
        add_lift(db, user.id, sat() - timedelta(days=22), [(squat, [(225, 5)] * 5)])
        p = _rx(db, user.id, sat())
        assert any(ln["key"] == "anchor:back_squat" and ln["numbers"].get("verdict") == "e1rm_start" for ln in p.rationale)

    def test_e1rm_start_ignores_high_rep_sets(self, db, campaign_user, squat):
        user, _ = campaign_user
        add_lift(db, user.id, sat() - timedelta(days=30), [(squat, [(225, 5), (200, 12)])])
        p = _rx(db, user.id, sat())
        # 225×5 → e1RM 262.5 → × pct(5) × 0.90 = 202.5 → 200 (a 12-rep 280 e1RM would give 215)
        assert _work(_main(p))[0]["target_weight_lb"] == 200.0
        assert p.system_line.startswith("[START 200]")

    def test_e1rm_window_is_90_days(self, db, campaign_user, squat):
        user, _ = campaign_user
        add_lift(db, user.id, sat() - timedelta(days=95), [(squat, [(225, 5)])])
        p = _rx(db, user.id, sat())
        assert _work(_main(p))[0]["target_weight_lb"] is None

    def test_kg_profile_rounds_to_kg_steps_but_stores_lb(self, db, campaign_user, squat):
        user, _ = campaign_user
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        profile.preferred_unit = WeightUnit.KG
        db.commit()
        add_lift(db, user.id, sat(), [(squat, [(225, 5)] * 5)])
        p = _rx(db, user.id, sat(1))
        assert _work(_main(p))[0]["target_weight_lb"] == 231.5

    def test_dumbbell_family_rounds_to_2_5(self, db, campaign_user):
        user, _ = campaign_user
        incline = family_exercise(db, "Incline Dumbbell Press")
        add_lift(db, user.id, weekday(1), [(incline, [(35, 12)] * 3)])
        p = _rx(db, user.id, weekday(1, 1))
        ex = _main(p, "incline_db_bench_press")
        assert [s["target_weight_lb"] for s in ex["sets"]] == [37.5] * 3
        assert ex["role"] == "accessory"

    def test_progression_override_is_honored(self, db, campaign_user, squat):
        user, campaign = campaign_user
        add_lift(db, user.id, sat(), [(squat, [(225, 5)] * 5)])
        campaign.overrides = {"progression": {"back_squat": 10}}
        db.commit()
        work = _work(_main(_rx(db, user.id, sat(1))))
        assert [s["target_weight_lb"] for s in work] == [235.0] * 5

    def test_reps_override_is_honored(self, db, campaign_user, squat):
        user, campaign = campaign_user
        add_lift(db, user.id, sat(), [(squat, [(225, 5)] * 5)])
        campaign.overrides = {"reps": {"back_squat": {"sets": 3, "reps": [8, 8]}}}
        db.commit()
        work = _work(_main(_rx(db, user.id, sat(1))))
        assert len(work) == 3
        assert all((s["target_reps_lo"], s["target_reps_hi"]) == (8, 8) for s in work)
        # the 5×5 anchor is short of the new 8-rep target → weight holds, never jumps
        assert [s["target_weight_lb"] for s in work] == [225.0] * 3

    def test_goal_chip_appears_for_family_with_objective(self, db, campaign_user, squat):
        from app.services.goal_service import create_goal
        user, campaign = campaign_user
        create_goal(db, user.id, squat.id, 315, "lb", date.today() + timedelta(weeks=12), campaign_id=campaign.id)
        db.commit()
        p = _rx(db, user.id, sat())
        chip = _main(p)["goal"]
        assert chip["target_weight"] == 315 and chip["pace_status"] in ("on_track", "ahead", "behind")
        assert _main(p, "deadlift")["goal"] is None


class TestRuns:
    def test_easy_and_long_from_the_ramp(self, db, campaign_user):
        user, _ = campaign_user
        easy = _rx(db, user.id, weekday(0)).run
        assert easy == {"kind": "easy", "miles": 2.0, "hr_cap_bpm": 133, "note": None}
        long_run = _rx(db, user.id, weekday(3)).run
        assert (long_run["kind"], long_run["miles"]) == ("long", 3.0)
        p = _rx(db, user.id, weekday(0))
        assert p.system_line == "[EASY 2.0 MI] HR ≤ 133"
        assert any(ln["key"] == "run:target" and ln["numbers"]["week_target_miles"] == 7.0 for ln in p.rationale)

    def test_easy_runs_clamp_to_template_range(self, db, campaign_user):
        user, campaign = campaign_user
        campaign.overrides = {"week_miles": {MONDAY.isoformat(): 12.0}}   # remainder 9 / 2 = 4.5 → clamp 2.5
        db.commit()
        assert _rx(db, user.id, weekday(0)).run["miles"] == 2.5

    def test_hr_cap_override(self, db, campaign_user):
        user, _ = campaign_user
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        profile.age, profile.run_hr_cap_bpm = 40, 150
        db.commit()
        assert _rx(db, user.id, weekday(0)).run["hr_cap_bpm"] == 150


class TestModulation:
    @pytest.fixture
    def anchored(self, db, campaign_user, squat, deadlift):
        user, campaign = campaign_user
        leg_press = family_exercise(db, "Leg Press")
        add_lift(db, user.id, sat(), [(squat, [(225, 5)] * 5), (deadlift, [(315, 5)] * 4), (leg_press, [(360, 12)] * 3)])
        return user

    def test_peak_and_battle_ready_do_nothing(self, db, anchored):
        for score in (90, 71):
            p = _rx(db, anchored.id, sat(1), condition=condition(score))
            assert p.modulation is None
            assert _work(_main(p))[0]["target_weight_lb"] == 230.0
            assert f"CONDITION {score}" in p.system_line
        assert _rx(db, anchored.id, sat(1), condition=condition(71)).system_line == "[+5] LAST 225×5×5 · CONDITION 71 BATTLE READY"

    def test_strained_scales_main_and_drops_last_accessory_set(self, db, anchored):
        p = _rx(db, anchored.id, sat(1), condition=condition(55))
        assert p.modulation == {"band": "strained", "factor": 0.95, "note": p.modulation["note"]}
        assert [s["target_weight_lb"] for s in _work(_main(p))] == [220.0] * 5      # 230 × 0.95 = 218.5 → 220
        assert [s["target_weight_lb"] for s in _work(_main(p, "deadlift"))] == [320.0] * 4   # secondary untouched (+5 clean)
        assert len(_work(_main(p, "leg_press"))) == 2
        assert p.hunt_type == "lift"
        # the persisted base is untouched by modulation
        assert [s["target_weight_lb"] for s in _main(p)["sets"] if not s["is_warmup"]] != \
            [s["target_weight_lb"] for s in next(e for e in p.base["exercises"] if e["family_id"] == "back_squat")["sets"] if not s["is_warmup"]]

    def test_critical_downgrades_to_light(self, db, anchored):
        p = _rx(db, anchored.id, sat(1), condition=condition(30))
        assert p.hunt_type == "light"
        work = _work(_main(p))
        assert len(work) == 3 and [s["target_weight_lb"] for s in work] == [195.0] * 3   # 230 × 0.85 = 195.5 → 195
        assert any("REST" in n for n in p.notes)
        assert p.modulation["band"] == "critical"


def _gate(db, user_id, exercise, hunt, weight=245, reps=5):
    now = datetime.now(timezone.utc)
    gate = PRGate(
        user_id=user_id, exercise_id=exercise.id, family_id="back_squat", planned_hunt_id=hunt.id,
        rank="A", name="A-Rank Gate: Squat 245×5", target_weight=weight, target_reps=reps,
        target_e1rm=weight * (1 + reps / 30), baseline_e1rm=262.5, projected_e1rm=283, weekly_slope=2.4,
        condition_at_spawn=76, status=GateStatus.OPEN.value, spawned_at=now, expires_at=now + timedelta(days=7),
    )
    db.add(gate)
    db.commit()
    return gate


class TestGate:
    def test_gate_is_set_one_after_warmups_and_backs_off_ten_percent(self, db, campaign_user, squat):
        user, _ = campaign_user
        add_lift(db, user.id, sat(), [(squat, [(225, 5)] * 5)])
        hunt = hunt_for(db, user.id, sat(1))
        gate = _gate(db, user.id, squat, hunt)
        p = prescribe(db, hunt, condition=condition(76), guard_flags=[], gate=gate)
        sq = _main(p)
        work = _work(sq)
        assert work[0] == {"set_number": 1, "target_weight_lb": 245.0, "target_reps_lo": 5, "target_reps_hi": 5,
                           "target_rpe": None, "is_warmup": False, "is_gate_attempt": True}
        assert [s["target_weight_lb"] for s in work[1:]] == [205.0] * 5           # 230 × 0.9 = 207 → 205
        assert [s["set_number"] for s in work] == [1, 2, 3, 4, 5, 6]
        assert [s["set_number"] for s in sq["sets"] if s["is_warmup"]] == [1, 2, 3]
        assert "GATE 245×5" in p.system_line
        assert any(ln["key"] == "gate:back_squat" and ln["numbers"]["backoff_factor"] == 0.9 for ln in p.rationale)

    def test_strained_defers_the_gate(self, db, campaign_user, squat):
        user, _ = campaign_user
        add_lift(db, user.id, sat(), [(squat, [(225, 5)] * 5)])
        hunt = hunt_for(db, user.id, sat(1))
        gate = _gate(db, user.id, squat, hunt)
        p = prescribe(db, hunt, condition=condition(50), guard_flags=[], gate=gate)
        assert not any(s["is_gate_attempt"] for s in _main(p)["sets"])
        line = next(ln for ln in p.rationale if ln["key"] == "gate:back_squat")
        assert "deferred to the next" in line["text"] and line["numbers"]["deferred"] is True
        assert "GATE DEFERRED" in p.system_line


def _load_row(db, user_id, day, **kw):
    row = DailyTrainingLoad(user_id=user_id, local_date=day, **kw)
    db.add(row)
    db.commit()
    return row


class TestGuard:
    def test_run_acwr_high_cuts_twenty_percent_and_converts_to_easy(self, db, campaign_user):
        user, _ = campaign_user
        _load_row(db, user.id, weekday(3), run_acwr=1.42, miles_7d=6.0, miles_plan_7d=7.0)
        p = _rx(db, user.id, weekday(3), condition=condition(80), guard_flags=["run_acwr_high"])
        assert (p.run["kind"], p.run["miles"]) == ("easy", 2.4)
        line = next(ln for ln in p.rationale if ln["key"] == "guard:run_acwr_high")
        assert "1.42" in line["text"] and line["numbers"]["cut_miles"] == 2.4
        assert p.system_line.endswith("RUN ACWR HIGH")

    def test_run_acwr_high_with_low_condition_is_rest_decreed(self, db, campaign_user):
        user, _ = campaign_user
        _load_row(db, user.id, weekday(0), run_acwr=1.35, miles_7d=6.0, miles_plan_7d=7.0)
        p = _rx(db, user.id, weekday(0), condition=condition(60), guard_flags=["run_acwr_high"])
        assert p.hunt_type == "rest" and p.run is None
        assert p.notes[0].startswith("REST DECREED")
        assert p.system_line.startswith("[REST DECREED]")

    def test_run_acwr_critical_is_rest_decreed(self, db, campaign_user):
        user, _ = campaign_user
        _load_row(db, user.id, weekday(0), run_acwr=1.62, miles_7d=6.0, miles_plan_7d=7.0)
        p = _rx(db, user.id, weekday(0), condition=condition(90), guard_flags=["run_acwr_critical", "run_acwr_high"])
        assert p.hunt_type == "rest"
        line = next(ln for ln in p.rationale if ln["key"] == "guard:run_acwr_critical")
        assert line["numbers"] == {"run_acwr": 1.62, "condition": 90, "original_miles": 2.0, "cut_miles": 0.0}

    def test_ramp_high_caps_to_120_percent_of_plan(self, db, campaign_user):
        user, _ = campaign_user
        _load_row(db, user.id, weekday(2), miles_7d=7.5, miles_plan_7d=7.0)      # allowed = 8.4 − 7.5 = 0.9
        p = _rx(db, user.id, weekday(2), condition=condition(80), guard_flags=["ramp_high"])
        assert p.run["miles"] == 0.9
        line = next(ln for ln in p.rationale if ln["key"] == "guard:ramp_high")
        assert "7% ahead" in line["text"] and line["numbers"]["cut_miles"] == 0.9

    def test_ramp_high_without_load_row_is_skipped_and_said(self, db, campaign_user):
        user, _ = campaign_user
        p = _rx(db, user.id, weekday(2), condition=condition(80), guard_flags=["ramp_high"])
        assert p.run["miles"] == 2.0
        assert any(ln["key"] == "guard:ramp_high" and ln["numbers"].get("skipped") for ln in p.rationale)

    def test_long_run_share_caps_the_long_run_only(self, db, campaign_user):
        user, _ = campaign_user
        _load_row(db, user.id, weekday(3), miles_7d=5.0)
        p = _rx(db, user.id, weekday(3), condition=condition(80), guard_flags=["long_run_share"])
        assert p.run["miles"] == 2.0                                      # 40% of 5.0 < 3.0
        _load_row(db, user.id, weekday(0), miles_7d=5.0)
        assert _rx(db, user.id, weekday(0), condition=condition(80), guard_flags=["long_run_share"]).run["miles"] == 2.0

    def test_deload_due_scales_runs_and_drops_a_main_set(self, db, campaign_user, squat):
        user, _ = campaign_user
        assert _rx(db, user.id, weekday(0), guard_flags=["deload_due"]).run["miles"] == 1.5
        add_lift(db, user.id, sat(), [(squat, [(225, 5)] * 5)])
        p = _rx(db, user.id, sat(1), guard_flags=["deload_due"])
        assert len(_work(_main(p))) == 4
        assert any(ln["key"] == "guard:deload_due" for ln in p.rationale)

    def test_flags_are_priority_ordered(self, db, campaign_user):
        user, _ = campaign_user
        p = _rx(db, user.id, sat(), guard_flags=["deload_due", "ramp_high"])
        assert p.guard_flags == ["ramp_high", "deload_due"]


class TestProgressionVerdicts:
    def test_rows_for_families_trained_that_week(self, db, campaign_user, squat, deadlift):
        user, _ = campaign_user
        add_lift(db, user.id, sat(), [(squat, [(225, 5)] * 5), (deadlift, [(315, 5)] * 3 + [(315, 4)])])
        rows = {r["family_id"]: r for r in progression_verdicts(db, user.id, MONDAY)}
        assert rows["back_squat"]["verdict"] == "progress"
        assert (rows["back_squat"]["last_weight_lb"], rows["back_squat"]["next_weight_lb"]) == (225.0, 230.0)
        assert (rows["back_squat"]["sets_hit"], rows["back_squat"]["sets_total"], rows["back_squat"]["increment_lb"]) == (5, 5, 5.0)
        assert rows["deadlift"]["verdict"] == "hold"
        assert rows["deadlift"]["display_name"] == "Deadlift"
        assert progression_verdicts(db, user.id, MONDAY + timedelta(weeks=3)) == []

    def test_deload_lift_verdict_from_two_misses(self, db, campaign_user, squat):
        user, _ = campaign_user
        add_lift(db, user.id, sat() - timedelta(days=7), [(squat, [(225, 3)] * 5)])
        add_lift(db, user.id, sat(), [(squat, [(225, 3)] * 5)])
        rows = progression_verdicts(db, user.id, MONDAY)
        assert rows[0]["verdict"] == "deload_lift" and rows[0]["next_weight_lb"] == 200.0


class TestTodayEndpoint:
    def _setup(self, client, db, auth_headers, unique_email, monkeypatch, *, score=71, flags=(), gate=None):
        headers, user = auth_headers(email=unique_email("today"))
        import_plan(db, user.id)
        fake_condition(monkeypatch, score)
        import app.api.hunts as hunts_api
        monkeypatch.setattr(hunts_api, "_guard_flags", lambda db, user_id, d: list(flags))
        monkeypatch.setattr(hunts_api, "_gate_for", lambda db, user_id, hunt: gate)
        return headers, user

    def test_today_is_the_full_fetch_time_pipeline(self, client, db, auth_headers, unique_email, monkeypatch):
        headers, user = self._setup(client, db, auth_headers, unique_email, monkeypatch, score=71, flags=["ramp_high"])
        squat = family_exercise(db, "Barbell Back Squat")
        add_lift(db, user.id, sat() - timedelta(days=7), [(squat, [(225, 5)] * 5)])
        _load_row(db, user.id, sat(), miles_7d=9.0, miles_plan_7d=7.0)
        resp = client.get("/hunts/today", params={"client_date": sat().isoformat()}, headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) >= {"id", "campaign_id", "arc_id", "template_id", "date", "type", "title", "location_tag",
                             "status", "session_id", "moved_to", "prescription", "rationale", "system_line",
                             "modulation", "guard_flags"}
        assert (body["date"], body["type"], body["title"], body["status"]) == (sat().isoformat(), "lift", "Squat Day — Heavy", "planned")
        assert body["guard_flags"] == ["ramp_high"]
        assert body["modulation"] is None
        assert body["system_line"] == "[+5] LAST 225×5×5 · CONDITION 71 BATTLE READY · RAMP HIGH"
        squat_rx = body["prescription"]["exercises"][0]
        assert squat_rx["role"] == "main" and squat_rx["family_id"] == "back_squat"
        assert [s["target_weight_lb"] for s in squat_rx["sets"] if not s["is_warmup"]] == [230.0] * 5
        # 14 days materialized; the base prescription persisted without modulation
        assert db.query(PlannedHunt).filter(PlannedHunt.user_id == user.id).count() == 14
        hunt = db.query(PlannedHunt).get(body["id"])
        assert hunt.prescription["exercises"][0]["sets"][-1]["target_weight_lb"] == 230.0

    def test_run_day_guard_rationale_is_persisted_once(self, client, db, auth_headers, unique_email, monkeypatch):
        headers, user = self._setup(client, db, auth_headers, unique_email, monkeypatch, score=80, flags=["run_acwr_high"])
        _load_row(db, user.id, weekday(0), run_acwr=1.4, miles_7d=5.0, miles_plan_7d=7.0)
        for _ in range(2):
            resp = client.get("/hunts/today", params={"client_date": weekday(0).isoformat()}, headers=headers)
            assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["prescription"]["run"]["miles"] == 1.6
        hunt = db.query(PlannedHunt).get(body["id"])
        guard_lines = [ln for ln in hunt.rationale if ln["key"].startswith("guard:")]
        assert len(guard_lines) == 1 and guard_lines[0]["numbers"]["cut_miles"] == 1.6
        assert hunt.prescription["run"]["miles"] == 2.0     # stored base never modulated

    def test_strained_modulation_and_gate_deferral_end_to_end(self, client, db, auth_headers, unique_email, monkeypatch):
        headers, user = self._setup(client, db, auth_headers, unique_email, monkeypatch, score=50)
        squat = family_exercise(db, "Barbell Back Squat")
        add_lift(db, user.id, sat() - timedelta(days=7), [(squat, [(225, 5)] * 5)])
        materialize_range(db, user.id, sat(), sat(), today=sat())
        db.commit()
        gate = _gate(db, user.id, squat, hunt_for(db, user.id, sat()))
        import app.api.hunts as hunts_api
        monkeypatch.setattr(hunts_api, "_gate_for", lambda db, user_id, hunt: gate)
        body = client.get("/hunts/today", params={"client_date": sat().isoformat()}, headers=headers).json()
        assert body["modulation"]["band"] == "strained"
        assert [s["target_weight_lb"] for s in body["prescription"]["exercises"][0]["sets"] if not s["is_warmup"]] == [220.0] * 5
        assert "GATE DEFERRED" in body["system_line"]

    def test_null_on_a_day_without_a_template(self, client, db, auth_headers, unique_email, monkeypatch):
        headers, user = auth_headers(email=unique_email("today-null"))
        phases = load_phases()
        for phase in phases:
            phase["days"] = [d for d in phase["days"] if d["name"] != "Wednesday"]
        import_plan(db, user.id, phases=phases)
        fake_condition(monkeypatch, 80)
        resp = client.get("/hunts/today", params={"client_date": weekday(2).isoformat()}, headers=headers)
        assert resp.status_code == 200 and resp.json() is None
        resp = client.get("/hunts/today", params={"client_date": (MONDAY - timedelta(days=1)).isoformat()}, headers=headers)
        assert resp.json() is None

    def test_null_without_campaign(self, client, auth_headers, unique_email):
        headers, _ = auth_headers(email=unique_email("today-none"))
        assert client.get("/hunts/today", headers=headers).json() is None

    def test_bad_client_date_is_400(self, client, auth_headers, unique_email):
        headers, _ = auth_headers(email=unique_email("today-bad"))
        assert client.get("/hunts/today", params={"client_date": "yesterday"}, headers=headers).status_code == 400


class TestWeekEndpoint:
    def test_pace_strip_math(self, client, db, auth_headers, unique_email):
        headers, user = auth_headers(email=unique_email("week"))
        import_plan(db, user.id)
        add_run(db, user.id, weekday(0), 2.4)
        add_run(db, user.id, weekday(2), 3.1)
        resp = client.get("/hunts/week", params={"start": weekday(3).isoformat(), "client_date": sat().isoformat()}, headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["week_start"] == MONDAY.isoformat()
        assert len(body["hunts"]) == 7 and [h["date"] for h in body["hunts"]] == [weekday(i).isoformat() for i in range(7)]
        assert (body["target_miles"], body["logged_miles"], body["lifts_planned"], body["lifts_done"]) == (7.0, 5.5, 2, 0)
        assert body["pace_status"] == "on_pace"         # 5.5 / (7 × 6/7 = 6.0) = 0.92
        assert body["campaign_week"] == 1
        # past days flipped to skipped, today and later still planned
        assert [h["status"] for h in body["hunts"]] == ["skipped"] * 5 + ["planned"] * 2
        assert all(h["system_line"] for h in body["hunts"])

    def test_pace_behind_and_ahead(self, client, db, auth_headers, unique_email):
        headers, user = auth_headers(email=unique_email("week-pace"))
        import_plan(db, user.id)
        add_run(db, user.id, weekday(0), 1.0)
        params = {"start": MONDAY.isoformat(), "client_date": sat().isoformat()}
        assert client.get("/hunts/week", params=params, headers=headers).json()["pace_status"] == "behind"
        add_run(db, user.id, weekday(2), 7.0)
        assert client.get("/hunts/week", params=params, headers=headers).json()["pace_status"] == "ahead"

    def test_linked_session_summary(self, client, db, auth_headers, unique_email):
        headers, user = auth_headers(email=unique_email("week-link"))
        import_plan(db, user.id)
        materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=6), today=MONDAY)
        db.commit()
        run = add_run(db, user.id, weekday(0), 2.0)
        campaign_service.link_session_to_plan(db, run)
        db.commit()
        body = client.get("/hunts/week", params={"start": MONDAY.isoformat(), "client_date": weekday(0).isoformat()}, headers=headers).json()
        mon = body["hunts"][0]
        assert mon["status"] == "done" and mon["session_id"] == run.id
        assert mon["session_summary"]["distance_miles"] == 2.0 and mon["session_summary"]["local_date"] == weekday(0).isoformat()

    def test_empty_week_without_campaign(self, client, auth_headers, unique_email):
        headers, _ = auth_headers(email=unique_email("week-none"))
        body = client.get("/hunts/week", headers=headers).json()
        assert body["hunts"] == [] and body["target_miles"] is None


class TestUpdateEndpoint:
    @pytest.fixture
    def ready(self, client, db, auth_headers, unique_email):
        headers, user = auth_headers(email=unique_email("put"))
        import_plan(db, user.id)
        materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=13), today=MONDAY)
        db.commit()
        return headers, user

    def test_skip(self, client, db, ready):
        headers, user = ready
        hunt = hunt_for(db, user.id, weekday(1))
        resp = client.put(f"/hunts/{hunt.id}", json={"status": "skipped"}, headers=headers)
        assert resp.status_code == 200 and resp.json()["status"] == "skipped"
        assert client.put(f"/hunts/{hunt.id}", json={"status": "skipped"}, headers=headers).status_code == 400
        assert client.put(f"/hunts/{hunt.id}", json={"status": "done"}, headers=headers).status_code == 422

    def test_move(self, client, db, ready):
        headers, user = ready
        hunt = hunt_for(db, user.id, sun())
        resp = client.put(f"/hunts/{hunt.id}", json={"moved_to": weekday(0, 1).isoformat()}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert (resp.json()["status"], resp.json()["moved_to"]) == ("moved", weekday(0, 1).isoformat())
        rows = db.query(PlannedHunt).filter(PlannedHunt.user_id == user.id, PlannedHunt.date == weekday(0, 1)).all()
        assert {r.template.type for r in rows} == {"run", "lift"}
        new = next(r for r in rows if r.template.type == "lift")
        assert new.status == PlannedHuntStatus.PLANNED.value and new.week_start == MONDAY + timedelta(days=7)
        assert client.put(f"/hunts/{hunt.id}", json={"moved_to": weekday(2, 1).isoformat()}, headers=headers).status_code == 400

    def test_swap(self, client, db, ready):
        headers, user = ready
        a, b = hunt_for(db, user.id, weekday(0)), hunt_for(db, user.id, sat())
        resp = client.put(f"/hunts/{a.id}", json={"swap_with": b.id}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["type"] == "lift" and resp.json()["date"] == weekday(0).isoformat()
        assert hunt_for(db, user.id, sat()).template.type == "run"
        assert client.put(f"/hunts/{a.id}", json={"swap_with": "nope"}, headers=headers).status_code == 404
        assert client.put(f"/hunts/{a.id}", json={"status": "skipped", "swap_with": b.id}, headers=headers).status_code == 422

    def test_other_users_hunt_is_404(self, client, db, ready, auth_headers, unique_email):
        headers, user = ready
        other_headers, _ = auth_headers(email=unique_email("put-other"))
        hunt = hunt_for(db, user.id, weekday(1))
        assert client.put(f"/hunts/{hunt.id}", json={"status": "skipped"}, headers=other_headers).status_code == 404


class TestLastPerformance:
    def test_404_when_never_performed(self, client, db, auth_headers, unique_email, squat):
        headers, _ = auth_headers(email=unique_email("last-none"))
        assert client.get(f"/exercises/{squat.id}/last-performance", headers=headers).status_code == 404

    def test_spans_the_family_and_reports_best_e1rm(self, client, db, auth_headers, unique_email, squat):
        headers, user = auth_headers(email=unique_email("last"))
        alias = family_exercise(db, "Squat")           # same family, different exercise row
        add_lift(db, user.id, sat() - timedelta(days=30), [(squat, [(245, 3)])])
        add_lift(db, user.id, sat(), [(alias, [(135, 5, None, True), (225, 5, 8), (225, 5, 9)])])
        resp = client.get(f"/exercises/{squat.id}/last-performance",
                          params={"client_date": (sat() + timedelta(days=3)).isoformat()}, headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert (body["exercise_id"], body["family_id"], body["date"], body["days_ago"]) == (squat.id, "back_squat", sat().isoformat(), 3)
        assert body["sets"] == [
            {"weight_lb": 135.0, "reps": 5, "rpe": None, "is_warmup": True},
            {"weight_lb": 225.0, "reps": 5, "rpe": 8, "is_warmup": False},
            {"weight_lb": 225.0, "reps": 5, "rpe": 9, "is_warmup": False},
        ]
        assert body["best_e1rm"] == pytest.approx(245 * 1.1, abs=0.1)
        assert body["best_e1rm_date"] == (sat() - timedelta(days=30)).isoformat()

    def test_matches_the_engine_anchor(self, db, create_test_user, squat):
        from app.services.prescription_service import last_performance
        user = make_user(create_test_user, "last-anchor")
        import_plan(db, user.id)
        materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=13), today=MONDAY)
        add_lift(db, user.id, sat(), [(squat, [(225, 5)] * 5)])
        db.commit()
        last = last_performance(db, user.id, squat, client_date=sat(1))
        p = _rx(db, user.id, sat(1))
        assert last["date"] == next(ln for ln in p.rationale if ln["key"] == "anchor:back_squat")["numbers"]["date"]
