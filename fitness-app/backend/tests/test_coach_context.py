"""
Athlete context builder (ARISE v3 §8.2) — key order, hashing, budget, and
every section against the seeded four-week athlete.
"""
from datetime import timedelta

import pytest

from app.services.coach_context_service import (
    SECTION_ORDER,
    TOKEN_BUDGET,
    build_context,
    context_hash,
    enforce_budget,
    estimate_tokens,
)
from tests.helpers_coach import (
    install_fake_w1,
    install_fake_w2,
    remove_w1,
    remove_w2,
    seed_four_weeks,
)


@pytest.fixture
def seeded(db, create_test_user, unique_email, monkeypatch):
    user, _ = create_test_user(email=unique_email("ctx"))
    s = seed_four_weeks(db, user)
    install_fake_w1(monkeypatch)
    install_fake_w2(monkeypatch)
    return s


def test_key_order_is_fixed(db, seeded):
    ctx = build_context(db, seeded.user.id, seeded.week_start)
    assert list(ctx.keys()) == list(SECTION_ORDER)
    assert ctx["version"] == "ctx_v1"
    assert ctx["week_start"] == seeded.week_start.isoformat()
    assert ctx["week_end"] == seeded.week_end.isoformat()


def test_context_hash_is_deterministic(db, seeded):
    a = build_context(db, seeded.user.id, seeded.week_start)
    b = build_context(db, seeded.user.id, seeded.week_start)
    assert context_hash(a) == context_hash(b)
    assert len(context_hash(a)) == 64
    b["profile"]["age"] = 33
    assert context_hash(a) != context_hash(b)


def test_token_estimate_under_budget(db, seeded):
    ctx = build_context(db, seeded.user.id, seeded.week_start)
    assert estimate_tokens(ctx) < TOKEN_BUDGET
    assert ctx["truncated"] == []


def test_every_trained_family_is_present(db, seeded):
    ctx = build_context(db, seeded.user.id, seeded.week_start)
    ids = {f["family_id"] for f in ctx["families"]}
    assert {"back_squat", "bench_press"} <= ids
    squat = next(f for f in ctx["families"] if f["family_id"] == "back_squat")
    assert squat["display_name"] == "Back Squat"
    assert squat["increment_lb"] == 5.0
    assert len(squat["weekly_best_e1rm"]) == 4
    assert squat["weekly_best_e1rm"][-1][0] == seeded.week_start.isoformat()
    assert squat["weekly_best_e1rm"][-1][1] == 280.0
    assert squat["best_e1rm_campaign"] == 280.0
    # trend_service owns the fit window (W2); the projection is 14 days of it.
    if squat["slope_6w"] is None:
        assert squat["projection_14d"] is None
    else:
        assert squat["slope_6w"] > 0
        assert squat["projection_14d"] == pytest.approx(round(280.0 + squat["slope_6w"] * 2, 1), abs=0.11)


def test_sessions_bucketed_on_local_date_without_warmups(db, seeded):
    ctx = build_context(db, seeded.user.id, seeded.week_start)
    weeks = ctx["sessions_4w"]
    assert [w["week_start"] for w in weeks] == [m.isoformat() for m in seeded.weeks]
    last = weeks[-1]
    assert len(last["lifts"]) == 2 and len(last["runs"]) == 3
    squat = next(lift for lift in last["lifts"] if lift["name"] == "Heavy Squat")
    assert squat["exercises"][0]["family"] == "back_squat"
    assert squat["exercises"][0]["sets"] == ["240x5@8"] * 5   # warm-up excluded
    assert last["run_miles"] == pytest.approx(11.0, abs=0.05)
    assert all(r["is_run"] and r["pace_sec_per_mile"] == 570 for r in last["runs"])


def test_campaign_section(db, seeded):
    ctx = build_context(db, seeded.user.id, seeded.week_start)
    camp = ctx["campaign"]
    assert camp["name"] == "Fall Base"
    assert camp["arc"] == {"name": "Base", "index": 0}
    assert camp["week_in_arc"] == 4 and camp["week_in_campaign"] == 4
    assert camp["deload"] is True            # week 4 of a 4-week cadence
    assert camp["deload_factor"] == 0.75
    assert camp["week_target_miles"] == 11.0
    assert camp["next_week_target_miles"] == 12.0
    assert len(camp["next_hunts"]) == 5
    dates = [h["date"] for h in camp["next_hunts"]]
    assert dates[0] == (seeded.next_week + timedelta(days=1)).isoformat()
    squat_day = next(h for h in camp["next_hunts"] if h["title"] == "Heavy Squat")
    assert squat_day["type"] == "lift" and squat_day["status"] == "planned"
    assert squat_day["lifts"] == [{"family": "back_squat", "role": "main", "sets": 5, "reps": 5, "weight_lb": None}]
    long_run = next(h for h in camp["next_hunts"] if h["title"] == "Long run")
    assert long_run["run"]["kind"] == "long"


def test_prescribed_hunt_summarizes_top_set(db, seeded):
    hunt = seeded.hunts[seeded.next_week + timedelta(days=5)]
    hunt.prescription = {
        "version": 1,
        "exercises": [{
            "family_id": "back_squat", "role": "main",
            "sets": [
                {"set_number": 1, "target_weight_lb": 135, "target_reps_lo": 5, "target_reps_hi": 5, "is_warmup": True},
                {"set_number": 2, "target_weight_lb": 245, "target_reps_lo": 5, "target_reps_hi": 5, "is_warmup": False},
                {"set_number": 3, "target_weight_lb": 245, "target_reps_lo": 5, "target_reps_hi": 5, "is_warmup": False},
            ],
        }],
        "run": None,
        "notes": [],
    }
    db.commit()
    ctx = build_context(db, seeded.user.id, seeded.week_start)
    squat_day = next(h for h in ctx["campaign"]["next_hunts"] if h["title"] == "Heavy Squat")
    assert squat_day["lifts"] == [{"family": "back_squat", "role": "main", "sets": 2, "reps": 5, "weight_lb": 245.0}]


def test_no_campaign_gives_null_section(db, create_test_user, unique_email, monkeypatch):
    user, _ = create_test_user(email=unique_email("nocamp"))
    s = seed_four_weeks(db, user, campaign=False)
    install_fake_w1(monkeypatch)
    install_fake_w2(monkeypatch)
    ctx = build_context(db, user.id, s.week_start)
    assert ctx["campaign"] is None
    assert ctx["candidates"]["adherence"] == {"planned": 0, "done": 0, "modified": 0, "moved": 0, "skipped": 0}
    assert {f["family_id"] for f in ctx["families"]} == {"back_squat", "bench_press"}


def test_without_w1_and_w2_the_fallbacks_hold(db, create_test_user, unique_email, monkeypatch):
    user, _ = create_test_user(email=unique_email("noW"))
    s = seed_four_weeks(db, user)
    remove_w1(monkeypatch)
    remove_w2(monkeypatch)
    ctx = build_context(db, user.id, s.week_start)
    # Direct-read fallbacks: the campaign row + its stamped ramp still show.
    assert ctx["campaign"]["name"] == "Fall Base"
    assert ctx["campaign"]["next_week_target_miles"] == 12.0
    assert ctx["load"] is None
    assert ctx["objectives"]["goals"][0]["goal_behind"] is False
    # Nothing W1-derived can appear; guard flags may still come from stored
    # daily_training_load rows (the documented W2 fallback).
    flags = {c["flag"] for c in ctx["candidates"]["concerns"]}
    assert not (flags & {"lift_stall", "goal_behind", "goal_ambitious"})


def test_condition_section_has_no_timestamp(db, seeded):
    ctx = build_context(db, seeded.user.id, seeded.week_start)
    cond = ctx["condition_today"]
    assert set(cond.keys()) == {"score", "band", "inputs", "muscles_cooling"}
    assert isinstance(cond["score"], int)
    assert cond["inputs"] and all(set(i.keys()) == {"key", "subscore"} for i in cond["inputs"])


def test_load_section_compresses_w2_state(db, seeded, monkeypatch):
    install_fake_w2(
        monkeypatch, flags=("ramp_high",), miles_7d=12.5, miles_plan_7d=11.0, run_acwr=1.12,
        series=[{"local_date": seeded.week_end.isoformat(), "run_load": 40.25, "lift_load": 30, "total_load": 70.4, "miles": 4.5, "run_acwr": 1.12}],
    )
    ctx = build_context(db, seeded.user.id, seeded.week_start)
    load = ctx["load"]
    assert load["flags"] == ["ramp_high"]
    assert load["run_acwr"] == 1.12 and load["miles_7d"] == 12.5
    assert load["series"] == [[seeded.week_end.isoformat(), 40.2, 70.4, 4.5]]


def test_wearable_and_profile_sections(db, seeded):
    ctx = build_context(db, seeded.user.id, seeded.week_start)
    wearable = ctx["wearable_14d"]
    assert len(wearable) == 14
    assert list(wearable[0].keys()) == ["local_date", "sleep_hours", "hrv", "resting_heart_rate", "recovery_score"]
    assert wearable[-1]["local_date"] == seeded.week_end.isoformat()
    assert wearable[-1]["sleep_hours"] == 7.3
    profile = ctx["profile"]
    assert profile["age"] == 32 and profile["sex"] == "M"
    assert profile["injury_notes"] == "Left knee: no deep lunges."
    assert profile["preferred_unit"] == "lb"


def test_objectives_section(db, seeded):
    ctx = build_context(db, seeded.user.id, seeded.week_start)
    obj = ctx["objectives"]
    assert len(obj["goals"]) == 1
    goal = obj["goals"][0]
    assert goal["goal_id"] == seeded.goal.id
    assert goal["family_id"] == "bench_press"
    assert goal["deadline_extensions"] == 0
    assert obj["pace"][0]["goal_id"] == seeded.goal.id
    assert obj["prs_week"] == [{
        "exercise": "Barbell Back Squat", "type": "e1rm", "weight_lb": 240.0, "reps": 5,
        "e1rm": 280.0, "date": (seeded.week_start + timedelta(days=5)).isoformat(),
    }]
    assert obj["gates_open"] == [] and obj["gates_closed_week"] == []


def test_enforce_budget_truncates_oldest_first(db, seeded):
    ctx = build_context(db, seeded.user.id, seeded.week_start)
    trimmed = enforce_budget(ctx, budget=1)
    assert "sessions_4w" in trimmed["truncated"]
    assert len(trimmed["sessions_4w"]) == 1
    assert trimmed["sessions_4w"][0]["week_start"] == seeded.week_start.isoformat()
    assert len(trimmed["wearable_14d"]) == 7
