"""Pipeline stages, one module per stage, and the runner that enforces the contract.

Seam: ``REGISTRY`` maps each ``StageId`` to a ``Stage`` built from its module
(see ``bookgen.stages.base`` for the contract). ``run_range`` is the only
caller of ``start_stage``/``finish_stage``. To implement a stage, edit its
``sNN_*.py`` module; CLI commands dispatch through ``run_range`` unchanged.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import ModuleType

from bookgen.manifest import add_flag, finish_stage, read_manifest, start_stage
from bookgen.models import StageId, StageStatus
from bookgen.providers.llm import LLMProvider
from bookgen.stages import (
    s00_intake,
    s01_appearance,
    s02_sheet,
    s03_bible,
    s04_plan,
    s05_manuscript,
    s06_briefs,
    s07_generate,
    s08_image_qa,
    s09_upscale,
    s10_layout,
    s11_preflight,
    s12_review,
    s13_ledger,
)
from bookgen.stages.base import Cadence, StageContext, StageInputError, StageResult


def _no_paths(ctx: StageContext) -> list[Path]:
    """Default ``inputs``/``outputs``: none declared."""
    return []


def _no_check(ctx: StageContext) -> None:
    """Default ``check``: nothing beyond declared inputs."""


@dataclass(frozen=True)
class Stage:
    """A stage module's contract, with defaults filled in."""

    id: StageId
    cadence: Cadence
    inputs: Callable[[StageContext], list[Path]]
    check: Callable[[StageContext], None]
    outputs: Callable[[StageContext], list[Path]]
    run: Callable[[StageContext], StageResult]

    @classmethod
    def from_module(cls, m: ModuleType) -> Stage:
        """Read ``STAGE_ID``, ``CADENCE`` and the optional hooks off a stage module."""
        return cls(
            id=m.STAGE_ID,
            cadence=m.CADENCE,
            inputs=getattr(m, "inputs", _no_paths),
            check=getattr(m, "check", _no_check),
            outputs=getattr(m, "outputs", _no_paths),
            run=m.run,
        )

    def manifest_episode(self, ctx: StageContext) -> int:
        """Which episode's manifest records this stage: ep01 for per-series stages."""
        return 1 if self.cadence in (Cadence.EVERY_RUN, Cadence.ONCE_PER_SERIES) else ctx.episode


_MODULES = (
    s00_intake,
    s01_appearance,
    s02_sheet,
    s03_bible,
    s04_plan,
    s05_manuscript,
    s06_briefs,
    s07_generate,
    s08_image_qa,
    s09_upscale,
    s10_layout,
    s11_preflight,
    s12_review,
    s13_ledger,
)

REGISTRY: dict[StageId, Stage] = {m.STAGE_ID: Stage.from_module(m) for m in _MODULES}
"""Stage id to contract, keyed by each module's own ``STAGE_ID``."""

if list(REGISTRY) != list(StageId):
    raise ImportError("every StageId needs exactly one stage module, in pipeline order")


class Outcome(StrEnum):
    """What the runner did with one stage."""

    SKIPPED = "skipped"
    DONE = "done"
    FLAGGED = "flagged"


@dataclass(frozen=True)
class StageReport:
    """One line of a run's report, for the CLI."""

    stage: StageId
    outcome: Outcome
    flags: int = 0
    cost_usd: float = 0.0


def stage_range(start: StageId, end: StageId) -> list[StageId]:
    """Stages from ``start`` to ``end`` inclusive, in pipeline order."""
    order = list(StageId)
    i, j = order.index(start), order.index(end)
    if i > j:
        raise ValueError(f"--from {start} comes after --to {end}")
    return order[i : j + 1]


def is_satisfied(stage: Stage, ctx: StageContext) -> bool:
    """True if ``stage`` ran to DONE or FLAGGED, its outputs exist, and no input changed since.

    An input modified after the stage finished (a forced upstream rerun, or the editor's
    hand edit) makes the stage stale, so it reruns instead of serving old output.
    """
    if stage.cadence is Cadence.EVERY_RUN:
        return False
    ep = stage.manifest_episode(ctx)
    rec = read_manifest(ctx.paths.manifest(ep), ep).stages.get(stage.id)
    if rec is None or rec.status not in (StageStatus.DONE, StageStatus.FLAGGED):
        return False
    if rec.finished is None or not all(p.exists() for p in stage.outputs(ctx)):
        return False
    return all(_mtime(p) <= rec.finished for p in stage.inputs(ctx) if p.exists())


def _mtime(path: Path) -> datetime:
    """A file's modification time as an aware UTC datetime."""
    return datetime.fromtimestamp(path.stat().st_mtime, UTC)


def check_inputs(stage: Stage, ctx: StageContext) -> None:
    """The §3.2 input gate: declared inputs exist, then the stage's own pure check."""
    missing = [p for p in stage.inputs(ctx) if not p.exists()]
    if missing:
        names = ", ".join(str(p.relative_to(ctx.paths.root)) for p in missing)
        raise StageInputError(f"{stage.id} is missing inputs: {names}")
    stage.check(ctx)


def run_stage(
    stage: Stage, ctx: StageContext, llm: LLMProvider | None = None, force: bool = False
) -> StageReport:
    """Run one stage under the contract; returns what happened.

    Raises ``StageInputError`` before anything is written if inputs fail, and
    re-raises any exception from the stage after recording it as FAILED.
    """
    if not force and is_satisfied(stage, ctx):
        return StageReport(stage.id, Outcome.SKIPPED)
    check_inputs(stage, ctx)
    ep = stage.manifest_episode(ctx)
    manifest = ctx.paths.manifest(ep)
    session = llm.session(stage.id, ctx.paths.logs(ep)) if llm else None
    start_stage(manifest, ep, stage.id)

    def cost() -> float:
        return session.cost_usd if session else 0.0

    try:
        result = stage.run(dataclasses.replace(ctx, llm=session))
    except BaseException:
        finish_stage(manifest, ep, stage.id, StageStatus.FAILED, cost_usd=cost())
        raise
    failed = [c for c in result.checks if not c.passed]
    for c in failed:
        add_flag(manifest, ep, stage.id, c.code, c.detail, spread=c.spread)
    status = StageStatus.FLAGGED if failed else StageStatus.DONE
    model = result.model or (session.models_used[0] if session and session.models_used else None)
    finish_stage(manifest, ep, stage.id, status, model=model, cost_usd=cost(), checks=result.checks)
    outcome = Outcome.FLAGGED if failed else Outcome.DONE
    return StageReport(stage.id, outcome, flags=len(failed), cost_usd=cost())


def run_range(
    ctx: StageContext,
    stages: list[StageId],
    llm: LLMProvider | None = None,
    force: bool | Collection[StageId] = False,
) -> list[StageReport]:
    """Run ``stages`` in order under the contract; stops at the first exception.

    ``force`` is ``True`` (every stage in the range) or the stages to rerun. Once a
    stage actually runs, every later stage in the range reruns too, since its inputs
    just changed.
    """
    forced = set(stages) if force is True else set(force or ())
    reports: list[StageReport] = []
    for s in stages:
        report = run_stage(REGISTRY[s], ctx, llm=llm, force=s in forced)
        reports.append(report)
        if report.outcome is not Outcome.SKIPPED:
            forced |= set(stages[stages.index(s) + 1 :])
    return reports


__all__ = [
    "REGISTRY",
    "Outcome",
    "Stage",
    "StageContext",
    "StageInputError",
    "StageReport",
    "run_range",
    "run_stage",
    "stage_range",
]
