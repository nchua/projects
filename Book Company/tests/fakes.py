"""A no-network LLM provider that returns canned structured responses."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from bookgen.models import StageId
from bookgen.prompts import Prompt
from bookgen.providers.llm import Effort, Role, model_for

Canned = BaseModel | Callable[[str], BaseModel]
"""A response, or a function of the user text that builds one."""

COST_PER_CALL = 0.01
"""What every fake call costs, so the manifest's per-stage cost is checkable."""


@dataclass
class Call:
    """One recorded call, for assertions."""

    stage: StageId
    label: str
    role: Role
    prompt: str
    context: list[str]
    user: str


@dataclass
class FakeSession:
    """Implements ``StageLLM``: pops canned responses by label, records every call."""

    llm: FakeLLM
    stage: StageId
    cost_usd: float = 0.0
    models_used: list[str] = field(default_factory=list)

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
        """Return the next canned response for ``label`` (validated as ``schema``)."""
        self.llm.calls.append(Call(self.stage, label, role, prompt.name, list(context), user))
        queue = self.llm.responses.get(label)
        if not queue:
            raise AssertionError(f"no canned response left for {label!r}")
        item = queue.pop(0)
        out = item(user) if callable(item) else item
        self.cost_usd += COST_PER_CALL
        model = model_for(role)
        if model not in self.models_used:
            self.models_used.append(model)
        return schema.model_validate(out.model_dump())


@dataclass
class FakeLLM:
    """Implements ``LLMProvider``; ``responses`` maps a call label to a queue."""

    responses: dict[str, list[Canned]]
    calls: list[Call] = field(default_factory=list)

    def session(self, stage: StageId, log_dir: Path) -> FakeSession:
        """A session for one stage run."""
        return FakeSession(self, stage)

    def labels(self) -> list[str]:
        """Labels of every call made so far, in order."""
        return [c.label for c in self.calls]
