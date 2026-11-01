"""S5 manuscript loop and S6 briefs on the fixture family, with a fake LLM."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from bookgen import cli
from bookgen.io import read_model, write_model
from bookgen.manifest import read_manifest
from bookgen.models import CritiqueLog, Ledger, Manuscript, SpreadText, StageId, StageStatus
from bookgen.providers.llm import Role
from bookgen.stages import Outcome, run_range
from bookgen.stages.base import StageContext
from bookgen.stages.s03_bible import JUDGE_CHECKS as BIBLE_CODES
from bookgen.stages.s04_plan import JUDGE_CHECKS as PLAN_CODES
from bookgen.stages.s05_manuscript import MAX_REVISIONS
from tests.canned import (
    critique,
    demo_bible,
    demo_briefs,
    demo_plan,
    draft,
    good_spreads,
    judgement,
)
from tests.conftest import open_flags
from tests.fakes import COST_PER_CALL, FakeLLM


@pytest.fixture
def ctx(demo_series: StageContext) -> StageContext:
    """The demo series with canned S3 and S4 artifacts (bible, side-cast folder, plan)."""
    write_model(demo_series.paths.bible, demo_bible(series_id="demo"))
    demo_series.paths.character_dir("mr_ferreira").mkdir(parents=True, exist_ok=True)
    write_model(demo_series.paths.plan(1), demo_plan())
    return demo_series


def _status(ctx: StageContext, stage: StageId) -> StageStatus:
    """A stage's status in ep01's manifest."""
    return read_manifest(ctx.paths.manifest(1), 1).stages[stage].status


def test_s5_stops_after_first_critique_when_everything_passes(ctx: StageContext) -> None:
    """Good draft, judge at the bar: no revise; manuscript and one critique round saved."""
    llm = FakeLLM({"draft": [draft()], "critique-0": [critique(3)]})
    [report] = run_range(ctx, [StageId.S5], llm=llm)
    assert report.outcome is Outcome.DONE, open_flags(ctx)
    assert llm.labels() == ["draft", "critique-0"]
    ms = read_model(ctx.paths.manuscript(1), Manuscript)
    assert ms.word_count == 401 and ms.stats["fk_grade"] <= 2.5
    assert len(read_model(ctx.paths.critique(1), CritiqueLog).rounds) == 1
    judge = llm.calls[1]
    assert judge.role is Role.JUDGE and judge.prompt == "critique"
    assert "fish kite" in judge.user  # sees the text, and only the text (§6.2)


def test_s5_round_limit_then_flag(ctx: StageContext) -> None:
    """A judge below the bar every time: exactly two revisions, then flags, not an exception."""
    low = critique(2, low={"delight": 1})  # mean < 2.3
    llm = FakeLLM(
        {
            "draft": [draft()],
            **{f"critique-{i}": [low] for i in range(MAX_REVISIONS + 1)},
            **{f"revise-{i}": [draft()] for i in range(1, MAX_REVISIONS + 1)},
        }
    )
    [report] = run_range(ctx, [StageId.S5], llm=llm)
    assert llm.labels() == [
        "draft",
        "critique-0",
        "revise-1",
        "critique-1",
        "revise-2",
        "critique-2",
    ]
    assert report.outcome is Outcome.FLAGGED
    assert "rubric_mean" in open_flags(ctx)
    assert len(read_model(ctx.paths.critique(1), CritiqueLog).rounds) == 3
    rec = read_manifest(ctx.paths.manifest(1), 1).stages[StageId.S5]
    assert rec.cost_usd == pytest.approx(6 * COST_PER_CALL)
    assert next(c for c in rec.checks if c.code == "rubric_delight").value == 1


def test_s5_mechanical_failure_forces_a_revise(ctx: StageContext) -> None:
    """Judge happy but a banned phrase present: revise gets the failure, then it passes."""
    bad = good_spreads()
    bad[1] = SpreadText(spread=2, text=bad[1].text + " It was a magical adventure.")
    llm = FakeLLM(
        {
            "draft": [draft(bad)],
            "critique-0": [critique(3)],
            "revise-1": [draft()],
            "critique-1": [critique(3)],
        }
    )
    [report] = run_range(ctx, [StageId.S5], llm=llm)
    assert report.outcome is Outcome.DONE
    revise = next(c for c in llm.calls if c.label == "revise-1")
    assert "banned_phrases" in revise.user and revise.role is Role.WRITER


def test_s6_briefs_pass_lint(ctx: StageContext) -> None:
    """Fifteen briefs that agree with the plan pass every lint check."""
    write_model(ctx.paths.manuscript(1), Manuscript(episode=1, spreads=good_spreads()))
    llm = FakeLLM({"briefs": [demo_briefs()]})
    [report] = run_range(ctx, [StageId.S6], llm=llm)
    assert report.outcome is Outcome.DONE, open_flags(ctx)
    assert ctx.paths.briefs(1).exists()


def test_s6_lint_flags_plan_mismatches(ctx: StageContext) -> None:
    """Wrong text side, a stranger with no folder, a missing slot, text in the art: flags."""
    write_model(ctx.paths.manuscript(1), Manuscript(episode=1, spreads=good_spreads()))
    briefs = demo_briefs()
    b = briefs.briefs
    b[0] = b[0].model_copy(update={"text_side": "right"})  # plan says left
    b[1] = b[1].model_copy(
        update={
            "characters": [*b[1].characters, b[1].characters[0].model_copy(update={"id": "zed"})]
        }
    )
    b[2] = b[2].model_copy(update={"scene": "A sign that reads BAKERY above the door"})
    briefs = briefs.model_copy(update={"briefs": b[:-1]})  # teaser missing
    llm = FakeLLM({"briefs": [briefs]})
    [report] = run_range(ctx, [StageId.S6], llm=llm)
    assert report.outcome is Outcome.FLAGGED
    assert set(open_flags(ctx)) == {
        "briefs_complete",
        "characters_have_sheets",
        "text_side_matches_plan",
        "characters_match_plan",
        "no_text_in_scene",
    }


def test_acceptance_flow_with_fake_llm(
    tmp_path: Path, demo_family_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """init-series, plan, write: bible, plan, manuscript and briefs; every stage costed."""
    llm = FakeLLM(
        {
            "bible": [demo_bible()],
            "bible-judge": [judgement(BIBLE_CODES)],
            "plan": [demo_plan()],
            "plan-judge": [judgement(PLAN_CODES)],
            "draft": [draft()],
            "critique-0": [critique(3)],
            "briefs": [demo_briefs()],
        }
    )
    monkeypatch.setattr(cli, "make_llm", lambda: llm)
    env = {"BOOKGEN_SERIES_DIR": str(tmp_path)}
    runner = CliRunner()
    steps = [
        ["init-series", "--family", str(demo_family_path)],
        ["plan", "--series", "demo", "--episode", "1", "--value", "perseverance"],
        ["write", "--series", "demo", "--episode", "1"],
    ]
    for args in steps:
        result = runner.invoke(cli.app, args, env=env)
        assert result.exit_code == 0, result.output
    root = tmp_path / "demo"
    for rel in ["series/bible.json", "ep01/plan.json", "ep01/manuscript.json", "ep01/briefs.json"]:
        assert (root / rel).exists(), rel
    stages = read_manifest(root / "ep01" / "manifest.json", 1).stages
    for s in (StageId.S3, StageId.S4, StageId.S5, StageId.S6):
        assert stages[s].cost_usd > 0 and stages[s].checks, s
    flags = runner.invoke(cli.app, ["flags", "--series", "demo"], env=env).output
    assert "bible_human_read" in flags


def test_s6_flags_each_failing_non_story_slot(ctx: StageContext) -> None:
    """Cover and teaser both failing the no-text negative give two flags, not one."""
    write_model(ctx.paths.manuscript(1), Manuscript(episode=1, spreads=good_spreads()))
    briefs = demo_briefs()
    b = [
        x.model_copy(update={"negatives": []}) if x.spread in ("cover", "teaser") else x
        for x in briefs.briefs
    ]
    llm = FakeLLM({"briefs": [briefs.model_copy(update={"briefs": b})]})
    run_range(ctx, [StageId.S6], llm=llm)
    assert open_flags(ctx).count("negatives_rule_out_text") == 2


def test_cli_reports_cost_cap_as_exit_3(
    ctx: StageContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A model-call failure is a one-line error with exit 3; the stage is recorded FAILED."""
    from bookgen.providers.llm import CostCapExceeded

    class Capped(FakeLLM):
        def session(self, stage: StageId, log_dir: Path) -> object:  # type: ignore[override]
            raise CostCapExceeded("over the $5.00 cap")

    monkeypatch.setattr(cli, "make_llm", lambda: Capped({}))
    result = CliRunner().invoke(
        cli.app, ["write", "--series", "demo"], env={"BOOKGEN_SERIES_DIR": str(tmp_path)}
    )
    assert result.exit_code == 3 and "CostCapExceeded" in result.output


def test_plan_judge_ledger_has_no_recap_summary(ctx: StageContext) -> None:
    """The standalone read gets the ledger without last_summary (it feeds the recap, §4.3)."""
    ledger = read_model(ctx.paths.ledger, Ledger).model_copy(
        update={"last_summary": "LAST TIME SUMMARY"}
    )
    write_model(ctx.paths.ledger, ledger)
    ctx.paths.plan(1).unlink()
    llm = FakeLLM({"plan": [demo_plan()], "plan-judge": [judgement(PLAN_CODES)]})
    run_range(ctx, [StageId.S4], llm=llm)
    planner, judge = llm.calls
    assert "LAST TIME SUMMARY" in planner.user and "LAST TIME SUMMARY" not in judge.user
