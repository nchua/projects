"""The minimal eval runner: scores per case, results file, deltas vs the previous run."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bookgen import cli
from bookgen.craft import PROJECT_ROOT
from bookgen.evals import latest_results, report, run_suite
from bookgen.stages.s03_bible import JUDGE_CHECKS as BIBLE_CODES
from bookgen.stages.s04_plan import JUDGE_CHECKS as PLAN_CODES
from tests.canned import critique, demo_bible, demo_plan, draft, judgement
from tests.fakes import FakeLLM


def _suite(tmp_path: Path) -> Path:
    """A one-case copy of evals/core (demo family x perseverance)."""
    d = tmp_path / "suite"
    d.mkdir()
    shutil.copy(PROJECT_ROOT / "evals" / "core" / "suite.yaml", d / "suite.yaml")
    text = (
        (d / "suite.yaml")
        .read_text()
        .replace("  - curiosity\n", "")
        .replace("  - big_feelings\n", "")
    )
    (d / "suite.yaml").write_text(text)
    return d


def _llm(score: int) -> FakeLLM:
    """Canned responses for one case whose judge gives every item ``score``."""
    return FakeLLM(
        {
            "bible": [demo_bible()],
            "bible-judge": [judgement(BIBLE_CODES)],
            "plan": [demo_plan()],
            "plan-judge": [judgement(PLAN_CODES)],
            "draft": [draft()],
            **{f"critique-{i}": [critique(score)] for i in range(3)},
            **{f"revise-{i}": [draft()] for i in (1, 2)},
        }
    )


def test_eval_writes_results_and_reports_deltas(tmp_path: Path) -> None:
    """Two runs: the second reports judge-mean and cost deltas against the first."""
    suite = _suite(tmp_path)
    first, prev = run_suite(suite, _llm(3), stamp="20261101T000000Z")
    assert prev is None
    [case] = first.cases
    assert case.error is None and case.judge_mean == 3.0 and case.judge_rounds == 1
    assert case.mechanical_failures == [] and case.cost_usd > 0
    assert "plan" in first.prompts and first.prompts["plan"].startswith("v1-")

    second, prev = run_suite(suite, _llm(2), stamp="20261101T010000Z")
    assert prev is not None and prev.stamp == first.stamp
    lines = report(second, prev)
    assert any("judge mean:" in ln and "(-1.00)" in ln for ln in lines)
    assert latest_results(suite / "results").stamp == second.stamp
    assert (
        suite / "runs" / second.stamp / "demo-perseverance" / "ep01" / "manuscript.json"
    ).exists()


def test_eval_records_a_failing_case_and_continues(tmp_path: Path) -> None:
    """A case that raises is recorded with its error, not fatal to the suite."""
    suite = _suite(tmp_path)
    run, _ = run_suite(suite, FakeLLM({}), stamp="20261101T000000Z")
    assert run.cases[0].error and "no canned response" in run.cases[0].error


def test_book_eval_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``book eval --suite`` prints per-case lines and totals."""
    suite = _suite(tmp_path)
    monkeypatch.setattr(cli, "make_llm", lambda: _llm(3))
    result = CliRunner().invoke(cli.app, ["eval", "--suite", str(suite)])
    assert result.exit_code == 0, result.output
    assert "demo/perseverance: judge 3.00" in result.output


def test_eval_builds_one_bible_per_family(tmp_path: Path) -> None:
    """Two values for one family: S3 runs once, its cost is counted once."""
    suite = _suite(tmp_path)
    (suite / "suite.yaml").write_text(
        (suite / "suite.yaml")
        .read_text()
        .replace("  - perseverance\n", "  - perseverance\n  - curiosity\n")
    )
    llm = FakeLLM(
        {
            "bible": [demo_bible()],
            "bible-judge": [judgement(BIBLE_CODES)],
            "plan": [demo_plan(), demo_plan()],
            "plan-judge": [judgement(PLAN_CODES), judgement(PLAN_CODES)],
            "draft": [draft(), draft()],
            "critique-0": [critique(3), critique(3)],
        }
    )
    run, _ = run_suite(suite, llm, stamp="20261101T000000Z")
    assert [c.value for c in run.cases] == ["perseverance", "curiosity"]
    assert all(c.error is None for c in run.cases)
    assert llm.labels().count("bible") == 1
    assert run.bible_cost_usd == {"demo": pytest.approx(0.02)}
    assert run.cost_usd == pytest.approx(0.02 + 2 * 0.04)
