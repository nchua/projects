"""The stage contract (SPEC §3.1, §3.2).

A stage module declares::

    STAGE_ID = StageId.S4
    CADENCE = Cadence.PER_EPISODE
    def inputs(ctx) -> list[Path]      # optional: artifacts that must exist (§3.2 input gate)
    def check(ctx) -> None             # optional: pure input checks; raise StageInputError
    def outputs(ctx) -> list[Path]     # optional: artifacts that mark the stage satisfied
    def run(ctx) -> StageResult        # the work; gate results come back as CheckResults

The runner (``bookgen.stages.run_range``) owns everything else: the skip test,
calling ``check`` before any write, ``start_stage``/``finish_stage``, recording
FAILED on an exception, turning failed checks into flags, and per-stage cost.
Stages never touch the manifest themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

from bookgen.models import CheckResult, Companion, StageId, Value
from bookgen.paths import SeriesPaths

if TYPE_CHECKING:
    from bookgen.providers.llm import StageLLM


class Cadence(StrEnum):
    """How often a stage runs (§3.2 "Runs" column); drives the skip test and manifest."""

    EVERY_RUN = "every_run"
    """Never skipped; idempotent by construction (S0). Recorded in ep01."""

    ONCE_PER_SERIES = "once_per_series"
    """Done once, recorded in ep01's manifest (S3)."""

    PER_EPISODE = "per_episode"
    """Done once per episode, recorded in that episode's manifest."""

    PER_CHARACTER = "per_character"
    """Done once per person (S1, S2); recorded in the run's episode manifest for now."""


class StageInputError(ValueError):
    """A stage's inputs are missing or invalid (§3.2 input gate). Exit code 2, never a flag."""


@dataclass(frozen=True)
class StageContext:
    """Inputs for one stage run. Only S0 uses the intake fields."""

    series_id: str | None = None
    """Series id; required for every stage (the CLI resolves S0's default)."""

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

    llm: StageLLM | None = None
    """Set by the runner for each stage: the metered, logging LLM session."""

    @property
    def paths(self) -> SeriesPaths:
        """The §3.4 layout for this series."""
        if self.series_id is None:
            raise StageInputError("a series id is required (--series)")
        return SeriesPaths.for_series(self.series_id, self.base_dir)

    def need_llm(self) -> StageLLM:
        """Return the LLM session, or fail loudly if the runner gave none."""
        if self.llm is None:
            raise StageInputError("this stage needs an LLM provider")
        return self.llm


@dataclass
class StageResult:
    """What a stage's ``run`` returns: its gate checks (§3.1). Failed checks become flags."""

    checks: list[CheckResult] = field(default_factory=list)
    """Every gate check, passed or failed; all of them land in the manifest."""

    model: str | None = None
    """Primary model id used, for the manifest record."""


def not_built(ref: StageId | str) -> NoReturn:
    """Raise the standard not-implemented error; ``ref`` is a stage id or a SPEC § ref."""
    where = f"§3.3 {ref}" if isinstance(ref, StageId) else ref
    raise NotImplementedError(f"not implemented (SPEC {where})")
