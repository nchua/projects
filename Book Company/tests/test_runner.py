"""The stage contract: check before write, FAILED on exception, cadence skip, flags not raises."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from bookgen.manifest import read_manifest
from bookgen.models import CheckResult, StageId, StageStatus
from bookgen.stages import Outcome, Stage, run_stage
from bookgen.stages.base import Cadence, StageContext, StageInputError, StageResult


def _stage(
    tmp_path: Path,
    *,
    cadence: Cadence = Cadence.PER_EPISODE,
    run: Callable[[StageContext], StageResult] | None = None,
    check: Callable[[StageContext], None] | None = None,
    inputs: list[str] | None = None,
) -> Stage:
    """A throwaway S4-shaped stage that writes ``out.txt`` in the episode folder."""

    def _run(ctx: StageContext) -> StageResult:
        out = ctx.paths.episode_dir(ctx.episode) / "out.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("x")
        return StageResult()

    return Stage(
        id=StageId.S4,
        cadence=cadence,
        inputs=lambda ctx: [ctx.paths.root / p for p in inputs or []],
        check=check or (lambda ctx: None),
        outputs=lambda ctx: [ctx.paths.episode_dir(ctx.episode) / "out.txt"],
        run=run or _run,
    )


def _ctx(tmp_path: Path, episode: int = 1) -> StageContext:
    """A context for series ``t`` under ``tmp_path``."""
    return StageContext(series_id="t", base_dir=tmp_path, episode=episode)


def test_check_runs_before_any_write(tmp_path: Path) -> None:
    """A failing input gate raises StageInputError and leaves no manifest record."""

    def bad(ctx: StageContext) -> None:
        raise StageInputError("nope")

    ctx = _ctx(tmp_path)
    with pytest.raises(StageInputError, match="nope"):
        run_stage(_stage(tmp_path, check=bad), ctx)
    with pytest.raises(StageInputError, match="missing inputs: series/bible.json"):
        run_stage(_stage(tmp_path, inputs=["series/bible.json"]), ctx)
    assert not ctx.paths.manifest(1).exists()


def test_exception_records_failed_and_reraises(tmp_path: Path) -> None:
    """An exception inside run is recorded as FAILED, then propagates."""

    def boom(ctx: StageContext) -> StageResult:
        raise RuntimeError("model fell over")

    ctx = _ctx(tmp_path)
    with pytest.raises(RuntimeError):
        run_stage(_stage(tmp_path, run=boom), ctx)
    rec = read_manifest(ctx.paths.manifest(1), 1).stages[StageId.S4]
    assert rec.status is StageStatus.FAILED and rec.finished


def test_done_stage_is_skipped_unless_forced(tmp_path: Path) -> None:
    """A DONE stage with its outputs present is skipped; --force reruns it."""
    ctx, stage = _ctx(tmp_path), _stage(tmp_path)
    assert run_stage(stage, ctx).outcome is Outcome.DONE
    assert run_stage(stage, ctx).outcome is Outcome.SKIPPED
    assert run_stage(stage, ctx, force=True).outcome is Outcome.DONE
    assert read_manifest(ctx.paths.manifest(1), 1).stages[StageId.S4].attempts == 2
    (ctx.paths.episode_dir(1) / "out.txt").unlink()  # output gone -> not satisfied
    assert run_stage(stage, ctx).outcome is Outcome.DONE


def test_cadence_decides_which_manifest_and_skip(tmp_path: Path) -> None:
    """Per-series stages record in ep01 and skip in later episodes; EVERY_RUN never skips."""
    series = _stage(tmp_path, cadence=Cadence.ONCE_PER_SERIES)
    series = Stage(**{**series.__dict__, "outputs": lambda ctx: []})
    run_stage(series, _ctx(tmp_path, episode=1))
    assert run_stage(series, _ctx(tmp_path, episode=2)).outcome is Outcome.SKIPPED
    assert not _ctx(tmp_path).paths.manifest(2).exists()

    per_ep = _stage(tmp_path)
    run_stage(per_ep, _ctx(tmp_path, episode=1))
    assert run_stage(per_ep, _ctx(tmp_path, episode=2)).outcome is Outcome.DONE

    always = Stage(**{**per_ep.__dict__, "cadence": Cadence.EVERY_RUN})
    assert run_stage(always, _ctx(tmp_path, episode=1)).outcome is Outcome.DONE


def test_failed_checks_become_flags_not_exceptions(tmp_path: Path) -> None:
    """Failed checks write flags and FLAGGED; all checks land in the record; reruns supersede."""
    checks = [
        CheckResult(code="recap_length", passed=False, detail="61 > 60 words", value=61),
        CheckResult(code="beats", passed=True),
    ]

    def flagged(ctx: StageContext) -> StageResult:
        return StageResult(checks=checks)

    ctx = _ctx(tmp_path)
    report = run_stage(_stage(tmp_path, run=flagged), ctx)
    assert report.outcome is Outcome.FLAGGED and report.flags == 1
    m = read_manifest(ctx.paths.manifest(1), 1)
    assert m.stages[StageId.S4].status is StageStatus.FLAGGED
    assert [c.code for c in m.stages[StageId.S4].checks] == ["recap_length", "beats"]
    assert [(f.code, f.resolved) for f in m.flags] == [("recap_length", False)]

    run_stage(_stage(tmp_path, run=flagged), ctx, force=True)
    m = read_manifest(ctx.paths.manifest(1), 1)
    assert [f.resolved for f in m.flags] == [True, False]  # old one superseded
