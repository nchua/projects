"""LLM roles and the provider protocol (SPEC §8.4).

Writer and judge are deliberately different models (§6.2). Override with
``BOOKGEN_WRITER_MODEL`` / ``BOOKGEN_JUDGE_MODEL`` only for experiments; a
series' pinned models should not drift.

Seam: stages see a ``StageLLM`` on ``ctx.llm`` (one per stage run, made by the
runner from an ``LLMProvider``). It has one call, ``structured``, which returns
a validated Pydantic object and does the logging and cost metering itself.
``AnthropicProvider`` is the real one; tests use ``tests/fakes.py``.

Each call: Craft Guide and bible first as cached system blocks (§8.4), then the
role prompt; structured output from the Pydantic schema; ``fallbacks="default"``
so a safety-classifier refusal on an innocent children's prompt re-runs
server-side; a hard per-run cap from ``BOOKGEN_MAX_COST_USD`` (default $5).
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

import anthropic
from pydantic import BaseModel, ValidationError

from bookgen.prompts import Prompt, load_prompt

if TYPE_CHECKING:
    from bookgen.models import StageId

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


# --- The real client (anthropic SDK) ---------------------------------------------------

MAX_TOKENS = 16_000
"""Per call; adaptive thinking counts against it. Non-streaming stays under SDK timeouts."""

DEFAULT_EFFORT: dict[Role, Effort] = {Role.WRITER: "medium", Role.JUDGE: "high"}
"""Role defaults; stages raise effort for drafting and revising."""

FALLBACK_BETA = "server-side-fallback-2026-07-01"
"""Beta for ``fallbacks="default"``: a refusal re-runs server-side on the recommended model."""


@dataclass(frozen=True)
class Rates:
    """USD per million tokens."""

    input: float
    output: float
    cache_write: float
    cache_read: float


PRICES: dict[str, Rates] = {
    "claude-opus-5-5": Rates(4.0, 20.0, 5.0, 0.20),
    "claude-sonnet-5-5": Rates(2.0, 10.0, 2.5, 0.20),
    "claude-opus-5": Rates(5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-8": Rates(5.0, 25.0, 6.25, 0.50),
    "claude-sonnet-5": Rates(2.0, 10.0, 2.5, 0.20),
}
"""Published rates (§8.4, claude-api skill 2026-10-06); fallback targets included."""

_UNKNOWN_RATES = Rates(5.0, 25.0, 6.25, 0.50)
"""For a model not in the table (e.g. an unexpected fallback): the highest rates we know."""


def price(model: str, usage: dict[str, Any]) -> float:
    """Cost in USD of one response's ``usage`` block, billed at ``model``'s rates."""
    r = PRICES.get(model, _UNKNOWN_RATES)
    tokens = (
        (usage.get("input_tokens") or 0) * r.input
        + (usage.get("output_tokens") or 0) * r.output
        + (usage.get("cache_creation_input_tokens") or 0) * r.cache_write
        + (usage.get("cache_read_input_tokens") or 0) * r.cache_read
    )
    return tokens / 1_000_000


class CostCapExceeded(RuntimeError):
    """The next call could push this run past ``BOOKGEN_MAX_COST_USD``."""


class LLMRefusal(RuntimeError):
    """The model (and its server-side fallback) declined the request."""


class LLMOutputError(RuntimeError):
    """The response was truncated or still invalid after one corrective retry."""


class Budget:
    """A hard per-run cost cap shared by every stage of one CLI invocation."""

    def __init__(self, cap_usd: float | None = None) -> None:
        self.cap_usd = (
            cap_usd if cap_usd is not None else float(os.environ.get("BOOKGEN_MAX_COST_USD", "5"))
        )
        self.spent_usd = 0.0

    def reserve(self, model: str, prompt_chars: int, max_tokens: int) -> None:
        """Refuse a call whose worst case (all input uncached, full output) breaks the cap."""
        r = PRICES.get(model, _UNKNOWN_RATES)
        worst = (prompt_chars / 3 * r.input + max_tokens * r.output) / 1_000_000
        if self.spent_usd + worst > self.cap_usd:
            raise CostCapExceeded(
                f"spent ${self.spent_usd:.2f}; next {model} call could cost up to ${worst:.2f}, "
                f"over the ${self.cap_usd:.2f} cap (BOOKGEN_MAX_COST_USD)"
            )


def system_blocks(context: Sequence[str], prompt: Prompt) -> list[dict[str, Any]]:
    """Context blocks first, each a cache breakpoint (§8.4), then the role instructions."""
    blocks: list[dict[str, Any]] = [
        {"type": "text", "text": c, "cache_control": {"type": "ephemeral"}} for c in context
    ]
    return [*blocks, {"type": "text", "text": prompt.system}]


def prompt_hash(model: str, system: list[dict[str, Any]], user: str, schema: type) -> str:
    """SHA-256 of everything that determines the output (§3.1 replay key)."""
    payload = {
        "model": model,
        "system": [b["text"] for b in system],
        "user": user,
        "schema": schema.model_json_schema(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class AnthropicSession:
    """One stage run's calls through the anthropic SDK: logged, metered, capped."""

    def __init__(
        self, client: anthropic.Anthropic, budget: Budget, stage: StageId, log_dir: Path
    ) -> None:
        self._client = client
        self._budget = budget
        self._stage = stage
        self._log_dir = log_dir
        self._cost = 0.0
        self._models: list[str] = []

    @property
    def cost_usd(self) -> float:
        """Total cost of this stage run's calls so far."""
        return self._cost

    @property
    def models_used(self) -> list[str]:
        """Model ids that served this stage's calls, in first-use order."""
        return list(self._models)

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
        """Run one structured-output call; one corrective retry on invalid output."""
        model = model_for(role)
        system = system_blocks(context, prompt)
        effort = effort or DEFAULT_EFFORT[role]
        for attempt in (1, 2):
            self._budget.reserve(model, sum(len(b["text"]) for b in system) + len(user), MAX_TOKENS)
            raw = self._client.beta.messages.with_raw_response.parse(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system,  # type: ignore[arg-type]
                messages=[{"role": "user", "content": user}],
                output_format=schema,
                output_config={"effort": effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
            body: dict[str, Any] = raw.json()  # type: ignore[assignment]
            served = str(body.get("model") or model)
            cost = price(served, body.get("usage") or {})
            self._cost += cost
            self._budget.spent_usd += cost
            if served not in self._models:
                self._models.append(served)
            error = _response_error(body)
            parsed: M | None = None
            if error is None:
                try:
                    parsed = raw.parse().parsed_output
                    if parsed is None:
                        error = "no structured output in the response"
                except ValidationError as exc:
                    error = str(exc)
            self._log(label, attempt, prompt, model, system, user, schema, body, cost, error)
            if parsed is not None:
                return parsed
            if body.get("stop_reason") == "refusal":
                raise LLMRefusal(f"{self._stage} {label}: {error}")
            if attempt == 1 and body.get("stop_reason") != "max_tokens":
                user = user + "\n\n" + load_prompt("validation_retry").render(error=error or "")
                continue
            raise LLMOutputError(f"{self._stage} {label}: {error}")
        raise AssertionError("unreachable")

    def _log(
        self,
        label: str,
        attempt: int,
        prompt: Prompt,
        model: str,
        system: list[dict[str, Any]],
        user: str,
        schema: type,
        body: dict[str, Any],
        cost: float,
        error: str | None,
    ) -> None:
        """Write one call to ``epNN/logs/`` with its prompt hash, response and cost (§3.1)."""
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        record = {
            "stage": self._stage,
            "label": label,
            "attempt": attempt,
            "prompt": {"name": prompt.name, "version": prompt.version, "sha": prompt.sha},
            "prompt_hash": prompt_hash(model, system, user, schema),
            "model_requested": model,
            "model_served": body.get("model"),
            "request_id": body.get("id"),
            "stop_reason": body.get("stop_reason"),
            "usage": body.get("usage"),
            "cost_usd": round(cost, 6),
            "error": error,
            "request": {"system": [b["text"] for b in system], "user": user},
            "response": [b.get("text") for b in body.get("content", []) if b.get("type") == "text"],
        }
        self._log_dir.mkdir(parents=True, exist_ok=True)
        path = self._log_dir / f"{self._stage}-{label}-{stamp}.json"
        path.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")


def _response_error(body: dict[str, Any]) -> str | None:
    """A refusal or truncation, described; ``None`` if the response is usable."""
    reason = body.get("stop_reason")
    if reason == "refusal":
        details = body.get("stop_details") or {}
        return f"refused (category {details.get('category')}): {details.get('explanation')}"
    if reason == "max_tokens":
        return f"truncated at max_tokens={MAX_TOKENS}"
    return None


class AnthropicProvider:
    """The real ``LLMProvider``. The SDK reads ``ANTHROPIC_API_KEY`` (never stored here)."""

    def __init__(
        self, client: anthropic.Anthropic | None = None, budget: Budget | None = None
    ) -> None:
        self._client = client
        self.budget = budget or Budget()

    def session(self, stage: StageId, log_dir: Path) -> AnthropicSession:
        """Return a fresh session for ``stage`` that logs under ``log_dir``."""
        if self._client is None:
            self._client = anthropic.Anthropic()
        return AnthropicSession(self._client, self.budget, stage, log_dir)
