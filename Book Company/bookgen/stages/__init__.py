"""Pipeline stages, one module per stage (SPEC §3.2-§3.3).

Seam: ``REGISTRY`` maps each ``StageId`` to its module's ``run``. To add or
implement a stage, edit its ``sNN_*.py`` module; the CLI dispatches through
``REGISTRY`` and ``run_range``, so commands start working with no CLI change.
"""

from __future__ import annotations

from collections.abc import Callable

from bookgen.models import StageId
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
from bookgen.stages.base import StageContext

StageFn = Callable[[StageContext], object]
"""A stage entry point: ``run(ctx)``."""

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

REGISTRY: dict[StageId, StageFn] = {m.STAGE_ID: m.run for m in _MODULES}
"""Stage id to entry point, keyed by each module's own ``STAGE_ID``."""

if list(REGISTRY) != list(StageId):
    raise ImportError("every StageId needs exactly one stage module, in pipeline order")


def stage_range(start: StageId, end: StageId) -> list[StageId]:
    """Stages from ``start`` to ``end`` inclusive, in pipeline order."""
    order = list(StageId)
    i, j = order.index(start), order.index(end)
    if i > j:
        raise ValueError(f"--from {start} comes after --to {end}")
    return order[i : j + 1]


def run_range(ctx: StageContext, stages: list[StageId]) -> None:
    """Run ``stages`` in order; a NotImplementedError stops the run and propagates."""
    for stage in stages:
        REGISTRY[stage](ctx)


__all__ = ["REGISTRY", "StageContext", "StageFn", "run_range", "stage_range"]
