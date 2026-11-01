"""Minimal eval runner (SPEC §6.7): plan and manuscript stages over fixture families.

``book eval --suite evals/core`` reads ``suite.yaml`` (families × values), runs
S0, S3, S4 and S5 for each case into ``<suite>/runs/<stamp>/`` (gitignored),
and writes ``<suite>/results/<stamp>.json`` (committed, so history is diffable).
It then prints deltas against the previous results file: judge mean, mechanical
failures, plan flags and cost. One provider is shared across the whole run, so
``BOOKGEN_MAX_COST_USD`` caps the eval as a whole; a case that fails is recorded
with its error and the run continues, except on the cost cap, which stops it.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from bookgen.craft import CRAFT_DIR, PROJECT_ROOT
from bookgen.io import read_model, write_model
from bookgen.manifest import read_manifest
from bookgen.models import StageId, Value
from bookgen.prompts import load_prompt
from bookgen.providers.llm import CostCapExceeded, LLMProvider
from bookgen.stages import run_range
from bookgen.stages.base import StageContext
from bookgen.stages.s00_intake import load_intake

EVAL_STAGES = [StageId.S3, StageId.S4, StageId.S5]
"""The plan and manuscript stages (§6.7, session 2)."""


class Suite(BaseModel):
    """``suite.yaml``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Suite name.")
    families: list[Path] = Field(min_length=1, description="Intake JSONs, project-relative.")
    values: list[Value] = Field(min_length=1, description="Values to run for each family.")


class EvalCase(BaseModel):
    """One family × value result."""

    family: str
    value: Value
    judge_scores: dict[str, float] = Field(default_factory=dict)
    judge_mean: float | None = None
    judge_rounds: int | None = None
    mechanical_failures: list[str] = Field(default_factory=list)
    plan_flags: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0
    error: str | None = None


class EvalRun(BaseModel):
    """``results/<stamp>.json``."""

    suite: str
    stamp: str
    prompts: dict[str, str] = Field(description="Prompt name to 'v<version>-<sha>'.")
    cases: list[EvalCase]

    @property
    def judge_mean(self) -> float | None:
        """Mean of case judge means, over cases that produced one."""
        means = [c.judge_mean for c in self.cases if c.judge_mean is not None]
        return sum(means) / len(means) if means else None

    @property
    def mechanical_failures(self) -> int:
        """Total failing mechanical checks."""
        return sum(len(c.mechanical_failures) for c in self.cases)

    @property
    def plan_flags(self) -> int:
        """Total plan flags."""
        return sum(len(c.plan_flags) for c in self.cases)

    @property
    def cost_usd(self) -> float:
        """Total cost."""
        return sum(c.cost_usd for c in self.cases)


def load_suite(suite_dir: Path) -> Suite:
    """Read ``<suite_dir>/suite.yaml``."""
    return Suite.model_validate(yaml.safe_load((suite_dir / "suite.yaml").read_text()))


def prompt_versions() -> dict[str, str]:
    """Every prompt file's version and sha, so a result names the text that made it."""
    names = sorted(p.stem for p in (CRAFT_DIR / "prompts").glob("*.md") if p.stem != "README")
    return {n: f"v{load_prompt(n).version}-{load_prompt(n).sha}" for n in names}


def _collect(ctx: StageContext, case: EvalCase) -> EvalCase:
    """Read one case's scores, failures, flags and cost from its manifest."""
    m = read_manifest(ctx.paths.manifest(1), 1)
    case.cost_usd = round(sum(r.cost_usd for r in m.stages.values()), 6)
    if (s4 := m.stages.get(StageId.S4)) is not None:
        case.plan_flags = [c.code for c in s4.checks if not c.passed]
    if (s5 := m.stages.get(StageId.S5)) is not None:
        for c in s5.checks:
            if c.code == "rubric_mean":
                case.judge_mean = c.value
            elif c.code == "judge_rounds":
                case.judge_rounds = int(c.value or 0)
            elif c.code.startswith("rubric_") and c.value is not None:
                case.judge_scores[c.code.removeprefix("rubric_")] = c.value
            elif not c.passed:
                case.mechanical_failures.append(c.code)
    return case


def run_suite(
    suite_dir: Path, llm: LLMProvider, stamp: str | None = None
) -> tuple[EvalRun, EvalRun | None]:
    """Run every case; write results; return ``(this run, previous run or None)``."""
    suite = load_suite(suite_dir)
    stamp = stamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    results_dir = suite_dir / "results"
    previous = latest_results(results_dir)
    base = suite_dir / "runs" / stamp
    cases = []
    for family_path in suite.families:
        family_file = PROJECT_ROOT / family_path
        family_id = load_intake(StageContext(family_path=family_file)).id
        for value in suite.values:
            case = EvalCase(family=family_id, value=value)
            ctx = StageContext(
                series_id=f"{family_id}-{value}", base_dir=base, family_path=family_file
            )
            try:
                run_range(ctx, [StageId.S0])
                run_range(dataclasses.replace(ctx, value=value), EVAL_STAGES, llm=llm)
            except CostCapExceeded as exc:
                case.error = str(exc)
                cases.append(_collect(ctx, case))
                break
            except Exception as exc:  # noqa: BLE001 - record and carry on with the suite
                case.error = f"{type(exc).__name__}: {exc}"
            cases.append(_collect(ctx, case))
    run = EvalRun(suite=suite.name, stamp=stamp, prompts=prompt_versions(), cases=cases)
    write_model(results_dir / f"{stamp}.json", run)
    return run, previous


def latest_results(results_dir: Path) -> EvalRun | None:
    """The most recent results file, if any."""
    files = sorted(results_dir.glob("*.json"))
    return read_model(files[-1], EvalRun) if files else None


def report(run: EvalRun, previous: EvalRun | None) -> list[str]:
    """Human-readable lines: per-case scores, then totals with deltas vs ``previous``."""

    def delta(now: float | None, before: float | None, fmt: str) -> str:
        if now is None:
            return "n/a"
        if before is None:
            return format(now, fmt)
        return f"{now:{fmt}} ({now - before:+{fmt}})"

    lines = [f"suite {run.suite} @ {run.stamp}"]
    for c in run.cases:
        mean = f"{c.judge_mean:.2f}" if c.judge_mean is not None else "n/a"
        err = f"  ERROR {c.error}" if c.error else ""
        lines.append(
            f"  {c.family}/{c.value}: judge {mean}, mech fails {len(c.mechanical_failures)}, "
            f"plan flags {len(c.plan_flags)}, ${c.cost_usd:.3f}{err}"
        )
    p = previous
    totals = [
        ("judge mean", run.judge_mean, p.judge_mean if p else None, ".2f"),
        ("mechanical failures", run.mechanical_failures, p.mechanical_failures if p else None, "d"),
        ("plan flags", run.plan_flags, p.plan_flags if p else None, "d"),
        ("cost USD", run.cost_usd, p.cost_usd if p else None, ".3f"),
    ]
    lines += [f"{name + ':':<21}{delta(now, before, fmt)}" for name, now, before, fmt in totals]
    if p:
        changed = sorted(k for k in run.prompts if run.prompts[k] != p.prompts.get(k))
        lines.append(f"prompts changed since {p.stamp}: {changed or 'none'}")
    return lines
