"""What every stage receives (SPEC §3.1).

A stage is ``run(ctx: StageContext)``: artifacts on disk in, artifacts on disk
out, idempotent, re-runnable. Resolve paths via ``ctx.paths``; record progress
with ``bookgen.manifest``; report a failed gate with ``manifest.add_flag`` and
``StageStatus.FLAGGED`` rather than raising.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from bookgen.models import Companion, StageId, Value
from bookgen.paths import SeriesPaths


@dataclass(frozen=True)
class StageContext:
    """Inputs for one stage run. Only S0 uses the intake fields."""

    series_id: str | None = None
    """Series id; ``None`` only for S0, which defaults it to the family id."""

    episode: int = 1
    """Episode number the run belongs to."""

    base_dir: Path | None = None
    """Directory holding all series; ``None`` means ``paths.series_base()``."""

    spread: int | None = None
    """Restrict S7-S9 to one spread (``--spread 7``)."""

    character: str | None = None
    """S1-S2: the person or companion id (``book sheet --character``)."""

    value: Value | None = None
    """S4: this episode's value (``book plan --value``); ``None`` lets the planner pick."""

    family_path: Path | None = None
    """S0 only: the intake JSON (Phase 0: ``examples/family_demo.json``)."""

    style_id: str | None = None
    """S0 only: style bible id from ``craft/style_bibles/``."""

    companion: Companion | None = None
    """S0 only: overrides the profile's companion archetype (``--companion``)."""

    @property
    def paths(self) -> SeriesPaths:
        """The §3.4 layout for this series."""
        if self.series_id is None:
            raise ValueError("series_id is required for every stage after S0")
        return SeriesPaths.for_series(self.series_id, self.base_dir)


def not_built(ref: StageId | str) -> NoReturn:
    """Raise the standard not-implemented error; ``ref`` is a stage id or a SPEC § ref."""
    where = f"§3.3 {ref}" if isinstance(ref, StageId) else ref
    raise NotImplementedError(f"not implemented (SPEC {where})")
