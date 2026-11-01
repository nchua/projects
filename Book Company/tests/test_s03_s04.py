"""S3 bible and S4 plan on the fixture family, with a fake LLM (no network)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bookgen import cli
from bookgen.craft import load_craft_guide
from bookgen.io import read_model, write_model
from bookgen.manifest import read_manifest
from bookgen.models import (
    CastMember,
    EpisodePlan,
    LessonCovered,
    SeriesBible,
    StageId,
    StageStatus,
    Value,
)
from bookgen.stages import Outcome, run_range
from bookgen.stages.base import StageContext
from bookgen.stages.s03_bible import JUDGE_CHECKS as BIBLE_CODES
from bookgen.stages.s04_plan import JUDGE_CHECKS as PLAN_CODES
from tests.canned import demo_bible, demo_plan, judgement
from tests.conftest import open_flags
from tests.fakes import COST_PER_CALL, FakeLLM


@pytest.fixture
def ctx(demo_series: StageContext) -> StageContext:
    """A freshly initialised demo series."""
    return demo_series


def test_s3_writes_bible_and_always_flags_human_read(ctx: StageContext) -> None:
    """Bible written with code-owned fields; judge and checks recorded; human read flagged."""
    llm = FakeLLM({"bible": [demo_bible()], "bible-judge": [judgement(BIBLE_CODES)]})
    [report] = run_range(ctx, [StageId.S3], llm=llm)
    assert report.outcome is Outcome.FLAGGED
    bible = read_model(ctx.paths.bible, SeriesBible)
    assert bible.series_id == "demo" and bible.style_id == "gouache-warm"
    assert bible.forbidden[:3] == ["spiders", "getting lost from a parent", "hospitals"]
    assert ctx.paths.character_dir("mr_ferreira").is_dir()
    assert open_flags(ctx) == ["bible_human_read"]
    rec = read_manifest(ctx.paths.manifest(1), 1).stages[StageId.S3]
    assert rec.cost_usd == pytest.approx(2 * COST_PER_CALL)
    assert rec.model == "claude-opus-5-5"
    assert {c.code for c in rec.checks} >= {"cast_matches_profile", "judge_names_exact"}
    assert all(c.context[0] == load_craft_guide() for c in llm.calls)  # guide first (§8.4)


def test_s3_flags_wrong_names_and_judge_failures(ctx: StageContext) -> None:
    """A misspelled hero and a failed judge check are flags, not exceptions."""
    bible = demo_bible()
    cast = [c if c.id != "maya" else c.model_copy(update={"name": "Maia"}) for c in bible.cast]
    llm = FakeLLM(
        {
            "bible": [bible.model_copy(update={"cast": cast})],
            "bible-judge": [judgement(BIBLE_CODES, failing=["world_specific"])],
        }
    )
    run_range(ctx, [StageId.S3], llm=llm)
    assert set(open_flags(ctx)) == {
        "cast_matches_profile",
        "judge_world_specific",
        "bible_human_read",
    }


def test_s3_flags_cameo_without_consent(ctx: StageContext, demo_family_raw: dict) -> None:
    """A parent in the cast when the family did not consent to cameos fails the cast check."""
    profile = json.loads(ctx.paths.profile.read_text())
    profile["consent"]["family_cameos"] = False
    ctx.paths.profile.write_text(json.dumps(profile))
    llm = FakeLLM({"bible": [demo_bible()], "bible-judge": [judgement(BIBLE_CODES)]})
    run_range(ctx, [StageId.S3], llm=llm)
    rec = read_manifest(ctx.paths.manifest(1), 1).stages[StageId.S3]
    cast_check = next(c for c in rec.checks if c.code == "cast_matches_profile")
    assert not cast_check.passed and "dana appears without cameo consent" in cast_check.detail


def _with_bible(ctx: StageContext) -> None:
    """Put a valid bible in place and mark S3 done."""
    llm = FakeLLM({"bible": [demo_bible()], "bible-judge": [judgement(BIBLE_CODES)]})
    run_range(ctx, [StageId.S3], llm=llm)


def test_s4_plan_passes_and_judge_never_sees_recap(ctx: StageContext) -> None:
    """A good plan passes every check; the judge reads it without the recap (§4.5)."""
    _with_bible(ctx)
    llm = FakeLLM({"plan": [demo_plan(episode=99)], "plan-judge": [judgement(PLAN_CODES)]})
    [report] = run_range(ctx, [StageId.S4], llm=llm)
    assert report.outcome is Outcome.DONE, open_flags(ctx)
    plan = read_model(ctx.paths.plan(1), EpisodePlan)
    assert plan.episode == 1 and plan.value is Value.PERSEVERANCE
    judge = next(c for c in llm.calls if c.label == "plan-judge")
    assert "Welcome to Puddle Lane" not in judge.user
    assert '"series_bible"' in judge.context[1]  # bible is the second cached block


def test_s4_flags_countable_rule_breaks(ctx: StageContext) -> None:
    """Value at 8, a 61-word recap, an unknown setting and cast: flags, stage FLAGGED."""
    _with_bible(ctx)
    bad = demo_plan(value_lands_at=8, recap="word " * 61)
    bad.beats[3] = bad.beats[3].model_copy(update={"setting": "the moon", "characters": ["zed"]})
    llm = FakeLLM({"plan": [bad], "plan-judge": [judgement(PLAN_CODES, failing=["standalone"])]})
    [report] = run_range(ctx, [StageId.S4], llm=llm)
    assert report.outcome is Outcome.FLAGGED
    assert set(open_flags(ctx)) >= {
        "value_lands_9_11",
        "recap_length",
        "settings_known",
        "cast_known",
        "judge_standalone",
    }
    assert read_manifest(ctx.paths.manifest(1), 1).stages[StageId.S4].status is (
        StageStatus.FLAGGED
    )


def test_s4_rotation_repeats_and_season_values(ctx: StageContext) -> None:
    """Episode 2 may not repeat the template, a non-home setting, or a covered value."""
    _with_bible(ctx)
    write_model(ctx.paths.plan(1), demo_plan())
    ledger = json.loads(ctx.paths.ledger.read_text())
    ledger["lessons_covered"] = [LessonCovered(episode=1, value=Value.PERSEVERANCE).model_dump()]
    ctx.paths.ledger.write_text(json.dumps(ledger))
    ep2 = dataclasses.replace(ctx, episode=2)
    llm = FakeLLM({"plan": [demo_plan()], "plan-judge": [judgement(PLAN_CODES)]})
    run_range(ep2, [StageId.S4], llm=llm)
    assert set(open_flags(ep2, 2)) == {
        "template_rotates",
        "setting_not_repeated",
        "value_not_repeated",
    }
    templates_offered = next(c for c in llm.calls if c.label == "plan").user
    assert '"id":"quest"' not in templates_offered  # previous template not offered
    assert '"id":"mystery"' in templates_offered


def test_default_value_is_first_uncovered_priority(ctx: StageContext) -> None:
    """With no --value, the planner gets the first priority not yet covered."""
    from bookgen.stages.common import load_ledger, load_profile
    from bookgen.stages.s04_plan import choose_value

    no_value = dataclasses.replace(ctx, value=None)
    ledger = load_ledger(ctx.paths).model_copy(
        update={"lessons_covered": [LessonCovered(episode=1, value=Value.PERSEVERANCE)]}
    )
    assert choose_value(no_value, load_profile(ctx.paths), ledger) is Value.CURIOSITY


def test_book_plan_cli_runs_s3_once(
    ctx: StageContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``book plan`` runs S3 then S4; a second episode's plan skips S3."""
    llm = FakeLLM(
        {
            "bible": [demo_bible()],
            "bible-judge": [judgement(BIBLE_CODES)],
            "plan": [demo_plan(), demo_plan(template="mystery", value="curiosity")],
            "plan-judge": [judgement(PLAN_CODES), judgement(PLAN_CODES)],
        }
    )
    monkeypatch.setattr(cli, "make_llm", lambda: llm)
    env = {"BOOKGEN_SERIES_DIR": str(tmp_path)}
    runner = CliRunner()
    args = ["plan", "--series", "demo", "--episode", "1", "--value", "perseverance"]
    first = runner.invoke(cli.app, args, env=env)
    assert first.exit_code == 0, first.output
    assert "S3: flagged" in first.output and "S4: done" in first.output
    second = runner.invoke(cli.app, ["plan", "--series", "demo", "--episode", "2"], env=env)
    assert second.exit_code == 0, second.output
    assert "S3: skipped" in second.output
    assert llm.labels().count("bible") == 1


def test_bible_cast_ids_must_be_folder_safe() -> None:
    """Cast ids are person ids (lower snake case), since they name folders."""
    with pytest.raises(ValueError):
        CastMember(id="Mr Ferreira", name="x", role="side", pronouns="he/him", description="x")
