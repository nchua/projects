"""
Debrief model step + validators (ARISE v3 §8.4–8.7).

The SDK is mocked. Replay runs over three stored contexts under
``tests/fixtures/coach/``; the validators are pure functions of the context
so every bound is checked against the ``clean_week`` fixture without a DB.
"""
import copy
import json
import pathlib
from datetime import date, timedelta

import anthropic
import httpx
import pytest

from app.models.coach import CoachOutput
from app.schemas.coach import DebriefModelOutput
from app.services import debrief_service
from app.services.coach_context_service import SECTION_ORDER, TOKEN_BUDGET, estimate_tokens
from app.services.debrief_service import (
    MAX_ADJUSTMENTS,
    generation_allowed,
    get_or_create_debrief,
    normalize_concerns,
    validate_adjustments,
)
from tests.helpers_coach import (
    install_fake_model,
    install_fake_w1,
    install_fake_w2,
    model_output,
    seed_four_weeks,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "coach"
FIXTURE_NAMES = ["clean_week", "ramp_high_week", "goal_behind_week"]


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _adj(op, **params):
    return {"op": op, "reason": "test", "confidence": "medium", "source": "model", **params}


# ---------------------------------------------------------------------------
# Replay over stored contexts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_context_shape_and_budget(name):
    ctx = load_fixture(name)
    assert list(ctx.keys()) == list(SECTION_ORDER)
    assert estimate_tokens(ctx) < TOKEN_BUDGET
    assert {f["family_id"] for f in ctx["families"]} >= {"back_squat", "bench_press"}


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_replay_model_output_validates(name, monkeypatch):
    ctx = load_fixture(name)
    families = {f["family_id"] for f in ctx["families"]}
    extra = _adj("set_progression", family="back_squat", increment_lb=5.0)
    raw = model_output(ctx, adjustments=None)
    raw["adjustments"].append(extra)
    parsed = DebriefModelOutput.model_validate(raw)
    assert parsed.next_week_focus
    validated = validate_adjustments(ctx, [a.model_dump(mode="json") for a in parsed.adjustments])
    assert len(validated) <= MAX_ADJUSTMENTS
    for adj in validated:
        assert adj["id"] and adj["status"] in ("proposed", "out_of_bounds")
        if "family" in adj["params"]:
            assert adj["params"]["family"] in families
    # Everything the engine proposed (and the in-bounds extra) is proposed.
    engine_ops = [a for a in validated if a["source"] == "engine"]
    assert all(a["status"] == "proposed" for a in engine_ops)


def test_ramp_high_fixture_carries_flag_and_hold_op():
    ctx = load_fixture("ramp_high_week")
    flags = [c["flag"] for c in ctx["candidates"]["concerns"]]
    assert "ramp_high" in flags
    ops = {op["op"]: op for op in ctx["candidates"]["candidate_ops"]}
    assert ops["set_week_miles"]["miles"] == ctx["load"]["miles_plan_7d"]


def test_goal_behind_fixture_carries_objective_ops():
    ctx = load_fixture("goal_behind_week")
    flags = [c["flag"] for c in ctx["candidates"]["concerns"]]
    assert {"goal_behind", "lift_stall", "sleep_low"} <= set(flags)
    ops = {op["op"] for op in ctx["candidates"]["candidate_ops"]}
    assert {"change_reps", "set_goal_deadline", "deload_now"} <= ops


# ---------------------------------------------------------------------------
# Validator bounds (pure, on the clean fixture)
# ---------------------------------------------------------------------------


@pytest.fixture
def ctx():
    return load_fixture("clean_week")


def _next_week(ctx) -> date:
    return date.fromisoformat(ctx["week_start"]) + timedelta(days=7)


def _one(ctx, adj):
    return validate_adjustments(ctx, [adj])[0]


def test_miles_within_15_percent_passes_and_16_fails(ctx):
    plan = ctx["campaign"]["next_week_target_miles"]
    ok = _one(ctx, _adj("set_week_miles", week_start=_next_week(ctx).isoformat(), miles=round(plan * 1.10, 2)))
    assert ok["status"] == "proposed" and ok["validation_note"] is None
    bad = _one(ctx, _adj("set_week_miles", week_start=_next_week(ctx).isoformat(), miles=round(plan * 1.16, 2)))
    assert bad["status"] == "out_of_bounds"
    assert "outside ±15%" in bad["validation_note"]


def test_miles_out_of_band_allowed_with_deload(ctx):
    plan = ctx["campaign"]["next_week_target_miles"]
    out = validate_adjustments(ctx, [
        _adj("deload_now", scope="runs"),
        _adj("set_week_miles", week_start=_next_week(ctx).isoformat(), miles=round(plan * 0.7, 2)),
    ])
    assert [a["status"] for a in out] == ["proposed", "proposed"]


def test_miles_for_unknown_week_is_out_of_bounds(ctx):
    far = (_next_week(ctx) + timedelta(days=14)).isoformat()
    bad = _one(ctx, _adj("set_week_miles", week_start=far, miles=10))
    assert bad["status"] == "out_of_bounds" and "No arc target" in bad["validation_note"]


def test_increment_must_match_family(ctx):
    bad = _one(ctx, _adj("set_progression", family="back_squat", increment_lb=10))
    assert bad["status"] == "out_of_bounds" and "increment_lb must equal" in bad["validation_note"]
    ok = _one(ctx, _adj("set_progression", family="back_squat", increment_lb=5))
    assert ok["status"] == "proposed"


def test_unknown_family_is_out_of_bounds(ctx):
    bad = _one(ctx, _adj("set_progression", family="leg_press", increment_lb=5))
    assert bad["status"] == "out_of_bounds" and "Unknown family" in bad["validation_note"]
    bad = _one(ctx, _adj("change_reps", family="zercher_squat", sets=3, reps=[3, 3]))
    assert bad["status"] == "out_of_bounds"


def test_second_deload_within_three_weeks(ctx):
    recent = copy.deepcopy(ctx)
    recent["campaign"]["last_deload_week"] = (_next_week(ctx) - timedelta(days=7)).isoformat()
    bad = _one(recent, _adj("deload_now", scope="lifts"))
    assert bad["status"] == "out_of_bounds" and "One deload per 3 weeks" in bad["validation_note"]
    old = copy.deepcopy(ctx)
    old["campaign"]["last_deload_week"] = (_next_week(ctx) - timedelta(days=21)).isoformat()
    assert _one(old, _adj("deload_now", scope="lifts"))["status"] == "proposed"


def test_extend_arc_bound(ctx):
    assert _one(ctx, _adj("extend_arc", weeks=3))["status"] == "out_of_bounds"
    assert _one(ctx, _adj("extend_arc", weeks=2))["status"] == "proposed"


def test_goal_deadline_bounds(ctx):
    goal = ctx["objectives"]["goals"][0]
    current = date.fromisoformat(goal["deadline"])
    five = _one(ctx, _adj("set_goal_deadline", goal_id=goal["goal_id"], deadline=(current + timedelta(weeks=5)).isoformat()))
    assert five["status"] == "out_of_bounds" and "at most 4 weeks" in five["validation_note"]
    four = _one(ctx, _adj("set_goal_deadline", goal_id=goal["goal_id"], deadline=(current + timedelta(weeks=4)).isoformat()))
    assert four["status"] == "proposed"
    earlier = _one(ctx, _adj("set_goal_deadline", goal_id=goal["goal_id"], deadline=(current - timedelta(days=1)).isoformat()))
    assert earlier["status"] == "out_of_bounds" and "extend" in earlier["validation_note"]
    extended = copy.deepcopy(ctx)
    extended["objectives"]["goals"][0]["deadline_extensions"] = 1
    second = _one(extended, _adj("set_goal_deadline", goal_id=goal["goal_id"], deadline=(current + timedelta(weeks=2)).isoformat()))
    assert second["status"] == "out_of_bounds" and "already extended" in second["validation_note"]


def test_swap_days_needs_two_planned_days_next_week(ctx):
    dates = [h["date"] for h in ctx["campaign"]["next_hunts"]]
    assert _one(ctx, _adj("swap_days", a=dates[0], b=dates[1]))["status"] == "proposed"
    off_plan = (_next_week(ctx)).isoformat()   # Monday: no hunt planned
    assert _one(ctx, _adj("swap_days", a=dates[0], b=off_plan))["status"] == "out_of_bounds"
    this_week = ctx["week_start"]
    assert _one(ctx, _adj("swap_days", a=this_week, b=dates[0]))["status"] == "out_of_bounds"


def test_four_adjustments_drop_lowest_confidence(ctx):
    out = validate_adjustments(ctx, [
        dict(_adj("extend_arc", weeks=1), confidence="low"),
        dict(_adj("set_progression", family="back_squat", increment_lb=5), confidence="high"),
        dict(_adj("deload_now", scope="lifts"), confidence="medium"),
        dict(_adj("extend_arc", weeks=2), confidence="medium"),
    ])
    assert len(out) == 3
    assert [a["confidence"] for a in out] == ["high", "medium", "medium"]
    assert not any(a["op"] == "extend_arc" and a["params"]["weeks"] == 1 for a in out)


def test_model_concern_flags_are_coerced_to_engine_flags(ctx):
    engine_flags = [c["flag"] for c in ctx["candidates"]["concerns"]]
    out = normalize_concerns(ctx, [{"flag": "made_up", "text": "Something the model noticed."}])
    assert out[0] == {"flag": "other", "text": "Something the model noticed."}
    assert [c["flag"] for c in out[1:]] == engine_flags


# ---------------------------------------------------------------------------
# get_or_create_debrief with the SDK mocked
# ---------------------------------------------------------------------------


@pytest.fixture
def athlete(db, create_test_user, unique_email, monkeypatch):
    user, _ = create_test_user(email=unique_email("model"))
    s = seed_four_weeks(db, user, low_sleep_nights=3)
    install_fake_w1(monkeypatch)
    install_fake_w2(monkeypatch, flags=("ramp_high",), miles_7d=12.5, miles_plan_7d=11.0)
    monkeypatch.setattr(debrief_service, "notify_weekly_report_ready", lambda db, uid: None)
    return s


def _stored(db, user_id):
    return db.query(CoachOutput).filter(CoachOutput.user_id == user_id).all()


def test_model_success_is_stored_with_validated_adjustments(db, athlete, monkeypatch):
    from app.services.coach_context_service import build_context

    ctx = build_context(db, athlete.user.id, athlete.week_start)
    reply = model_output(ctx, summary="Ran 12.5 against 11.0 planned. Sleep slipped three nights.", focus="Hold the mileage; protect sleep.")
    reply["adjustments"].append(_adj("extend_arc", weeks=3, confidence="low"))
    calls = install_fake_model(monkeypatch, reply)

    row = get_or_create_debrief(db, athlete.user.id, athlete.week_start, client_date=athlete.week_end)
    assert row.source == "model" and row.model == "claude-opus-5" and row.prompt_version == "debrief_v1"
    assert row.output["summary"].startswith("Ran 12.5")
    assert row.validated["summary"] == reply["summary"]
    assert row.validated["adherence"]["done"] == 5
    assert row.validated["highlights"][0]["kind"] == "pr"
    statuses = {a["op"]: a["status"] for a in row.validated["adjustments"]}
    assert statuses["set_week_miles"] == "proposed"
    assert statuses["extend_arc"] == "out_of_bounds"
    assert row.validated["candidate_ops"] == ctx["candidates"]["candidate_ops"]
    assert row.context_hash and row.decisions == {}
    assert len(_stored(db, athlete.user.id)) == 1

    assert len(calls) == 1
    kwargs = calls[0]
    assert kwargs["model"] == "claude-opus-5"
    assert kwargs["output_format"] is DebriefModelOutput
    assert kwargs["output_config"] == {"effort": "high"}
    assert kwargs["betas"] == ["server-side-fallback-2026-06-01"]
    assert kwargs["fallbacks"] == [{"model": "claude-opus-4-8"}]
    assert "thinking" not in kwargs
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "# debrief_v1" in kwargs["system"][0]["text"]
    assert json.loads(kwargs["messages"][0]["content"])["week_start"] == athlete.week_start.isoformat()


@pytest.mark.parametrize("outcome,reason", [
    ("refusal", "refusal"),
    (anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")), "timeout"),
    ({"summary": "no adjustments key"}, "schema"),
])
def test_failures_fall_back_to_engine(db, athlete, monkeypatch, outcome, reason):
    install_fake_model(monkeypatch, outcome)
    row = get_or_create_debrief(db, athlete.user.id, athlete.week_start, client_date=athlete.week_end)
    assert row.source == "engine_fallback"
    assert row.output == {"failure": reason}
    assert row.validated["fallback_reason"] == reason
    assert row.validated["summary"].startswith("5 of 5 hunts done.")
    assert row.validated["summary"] == row.validated["engine_summary"]
    assert row.validated["next_week_focus"]
    ops = {a["op"] for a in row.validated["adjustments"]}
    assert "set_week_miles" in ops
    assert all(a["source"] == "engine" and a["status"] == "proposed" for a in row.validated["adjustments"])
    assert [c["flag"] for c in row.validated["concerns"]] == [c["flag"] for c in row.validated["concerns"]]
    assert len(_stored(db, athlete.user.id)) == 1


def test_second_get_returns_stored_row_without_model_call(db, athlete, monkeypatch):
    from app.services.coach_context_service import build_context

    ctx = build_context(db, athlete.user.id, athlete.week_start)
    calls = install_fake_model(monkeypatch, model_output(ctx))
    first = get_or_create_debrief(db, athlete.user.id, athlete.week_start, client_date=athlete.week_end)
    second = get_or_create_debrief(db, athlete.user.id, athlete.week_start, client_date=athlete.week_end)
    assert first.id == second.id and len(calls) == 1
    forced = get_or_create_debrief(db, athlete.user.id, athlete.week_start, client_date=athlete.week_end, force=True)
    assert forced.id == first.id and len(calls) == 2
    assert len(_stored(db, athlete.user.id)) == 1


def test_before_sunday_returns_engine_preview_without_storing(db, athlete, monkeypatch):
    calls = install_fake_model(monkeypatch, "refusal")
    wednesday = athlete.week_start + timedelta(days=2)
    row = get_or_create_debrief(db, athlete.user.id, athlete.week_start, client_date=wednesday)
    assert row.id.startswith("preview-") and row.source == "engine_fallback"
    assert row.validated["summary"]
    assert calls == [] and _stored(db, athlete.user.id) == []
    # Saturday with the Saturday hunt linked → allowed (on-demand rule).
    saturday = athlete.week_start + timedelta(days=5)
    assert generation_allowed(db, athlete.user.id, athlete.week_start, saturday) is True
    athlete.hunts[saturday].session_id = None
    db.commit()
    assert generation_allowed(db, athlete.user.id, athlete.week_start, saturday) is False
    assert generation_allowed(db, athlete.user.id, athlete.week_start, athlete.week_end) is True


def test_weekly_report_push_fires_once_on_first_store(db, athlete, monkeypatch):
    from unittest.mock import MagicMock

    push = MagicMock(return_value=None)
    monkeypatch.setattr(debrief_service, "notify_weekly_report_ready", push)
    install_fake_model(monkeypatch, "refusal")
    wednesday = athlete.week_start + timedelta(days=2)
    get_or_create_debrief(db, athlete.user.id, athlete.week_start, client_date=wednesday)
    assert push.call_count == 0                       # preview: nothing stored, no push
    get_or_create_debrief(db, athlete.user.id, athlete.week_start, client_date=athlete.week_end)
    assert push.call_count == 1                       # first store (fallback counts)
    get_or_create_debrief(db, athlete.user.id, athlete.week_start, client_date=athlete.week_end)
    get_or_create_debrief(db, athlete.user.id, athlete.week_start, client_date=athlete.week_end, force=True)
    assert push.call_count == 1                       # re-reads and regenerations never re-push
    push.assert_called_once_with(db, athlete.user.id)
