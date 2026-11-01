"""LLM roles and the provider protocol (SPEC §8.4).

Writer and judge are deliberately different models (§6.2). Override with
``BOOKGEN_WRITER_MODEL`` / ``BOOKGEN_JUDGE_MODEL`` only for experiments; a
series' pinned models should not drift.

Seam: stages see a ``StageLLM`` on ``ctx.llm`` (one per stage run, made by the
runner from an ``LLMProvider``). It has one call, ``structured``, which returns
a validated Pydantic object and does the logging and cost metering itself.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel

if TYPE_CHECKING:
    from bookgen.models import StageId
    from bookgen.prompts import Prompt

WRITER_MODEL: str = os.environ.get("BOOKGEN_WRITER_MODEL", "claude-opus-5-5")
"""Plan, draft, revise, briefs, bible (§8.4)."""

JUDGE_MODEL: str = os.environ.get("BOOKGEN_JUDGE_MODEL", "claude-sonnet-5-5")
"""Judge, critique, extraction, image QA (§8.4); never the writer model."""

Effort = Literal["low", "medium", "high", "xhigh", "max"]
"""``output_config.effort``; thinking depth and token spend."""


class Role(StrEnum):
    """What a model call is for; picks the model."""

    WRITER = "writer"
    JUDGE = "judge"


def model_for(role: Role) -> str:
    """Return the model id for ``role``; refuses a judge that is the writer (§6.2)."""
    if JUDGE_MODEL == WRITER_MODEL:
        raise RuntimeError(f"judge and writer must be different models (§6.2): {WRITER_MODEL}")
    return WRITER_MODEL if role is Role.WRITER else JUDGE_MODEL


class StageLLM(Protocol):
    """The LLM as one stage run sees it: structured calls, logged and metered."""

    @property
    def cost_usd(self) -> float:
        """Total cost of this stage run's calls so far."""
        ...

    @property
    def models_used(self) -> list[str]:
        """Model ids that served this stage's calls, in first-use order."""
        ...

    def structured[M: BaseModel](
        self,
        *,
        role: Role,
        label: str,
        prompt: Prompt,
        context: Sequence[str],
        user: str,
        schema: type[M],
        effort: Effort | None = None,
    ) -> M:
        """Run one call and return ``schema`` validated.

        Args:
            role: Picks the model (writer or judge).
            label: Short name for the log file and fakes, e.g. ``"plan"``, ``"critique-2"``.
            prompt: The versioned role prompt from ``craft/prompts/``.
            context: Stable blocks that go first, in order (Craft Guide, then bible), so
                prompt caching covers them (§8.4).
            user: The per-call inputs, rendered as text.
            schema: The structured-output model.
            effort: ``output_config.effort``; ``None`` uses the role default.
        """
        ...


class LLMProvider(Protocol):
    """Makes one ``StageLLM`` per stage run; the runner owns it."""

    def session(self, stage: StageId, log_dir: Path) -> StageLLM:
        """Return a fresh session for ``stage`` that logs under ``log_dir``."""
        ...
