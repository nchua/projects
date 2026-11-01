"""LLM roles (SPEC §8.4). Stub: no SDK, no calls until session 2.

Writer and judge are deliberately different models (§6.2). Override with
``BOOKGEN_WRITER_MODEL`` / ``BOOKGEN_JUDGE_MODEL`` only for experiments; a
series' pinned models should not drift. The API key will come from
``ANTHROPIC_API_KEY`` via the SDK; it is never read or stored here.
"""

from __future__ import annotations

import os
from enum import StrEnum

WRITER_MODEL: str = os.environ.get("BOOKGEN_WRITER_MODEL", "claude-opus-5-5")
"""Plan, draft, revise, briefs, bible (§8.4)."""

JUDGE_MODEL: str = os.environ.get("BOOKGEN_JUDGE_MODEL", "claude-sonnet-5-5")
"""Judge, critique, extraction, image QA (§8.4); never the writer model."""


class Role(StrEnum):
    """What a model call is for; picks the model."""

    WRITER = "writer"
    JUDGE = "judge"


def model_for(role: Role) -> str:
    """Return the model id for ``role``; refuses a judge that is the writer (§6.2)."""
    if JUDGE_MODEL == WRITER_MODEL:
        raise RuntimeError(f"judge and writer must be different models (§6.2): {WRITER_MODEL}")
    return WRITER_MODEL if role is Role.WRITER else JUDGE_MODEL
