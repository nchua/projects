"""Helpers shared by the text stages (S3-S6): loading inputs and rendering them.

Seam: context blocks are rendered here once, deterministically (same bytes for
the same artifact), so the Craft Guide and bible prefixes hit the prompt cache
across calls (§8.4). Prompt prose lives in ``craft/prompts/``, never here.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from bookgen.craft import (
    BandRule,
    TemplateEntry,
    ValueEntry,
    load_band_rules,
    load_craft_guide,
    load_templates,
    load_values,
)
from bookgen.io import read_model
from bookgen.models import (
    CheckResult,
    EpisodePlan,
    FamilyProfile,
    Judgement,
    Ledger,
    SeriesBible,
    Value,
)
from bookgen.paths import SeriesPaths


def as_json(data: BaseModel | Any, **dump: Any) -> str:  # noqa: ANN401 - any JSON-able value
    """Render a model or plain data as stable, indented JSON for a prompt."""
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json", **dump)
    return json.dumps(data, indent=2, ensure_ascii=False)


def writer_context(paths: SeriesPaths) -> list[str]:
    """Craft Guide, then the bible: the cached prefix of every post-S3 call (§8.4)."""
    bible = load_bible(paths).model_dump(mode="json")
    return [load_craft_guide(), as_json({"series_bible": bible})]


def load_profile(paths: SeriesPaths) -> FamilyProfile:
    """``family/profile.json``."""
    return read_model(paths.profile, FamilyProfile)


def load_bible(paths: SeriesPaths) -> SeriesBible:
    """``series/bible.json``."""
    return read_model(paths.bible, SeriesBible)


def load_ledger(paths: SeriesPaths) -> Ledger:
    """``series/ledger.json``."""
    return read_model(paths.ledger, Ledger)


def load_plan(paths: SeriesPaths, episode: int) -> EpisodePlan:
    """``epNN/plan.json``."""
    return read_model(paths.plan(episode), EpisodePlan)


def previous_plan(paths: SeriesPaths, episode: int) -> EpisodePlan | None:
    """The previous episode's plan, if there is one on disk (§4.4 rotation and repeats)."""
    prev = paths.plan(episode - 1)
    return read_model(prev, EpisodePlan) if episode > 1 and prev.exists() else None


def band_rule(profile: FamilyProfile) -> BandRule:
    """The hero's band rules (§1.2)."""
    return load_band_rules().bands[profile.hero.band]


def value_entry(value: Value) -> ValueEntry:
    """The catalog row for ``value`` (§1.5)."""
    return next(v for v in load_values() if v.id == value)


def template_entries() -> list[TemplateEntry]:
    """Every structure template (§4.4)."""
    return load_templates()


def judge_checks(
    judgement: Judgement, expected: dict[str, str], prefix: str = ""
) -> list[CheckResult]:
    """Map a judge's verdict onto ``CheckResult``s; a check the judge skipped fails.

    Args:
        judgement: The judge's structured output.
        expected: Check code to a short description, as listed in the judge prompt.
        prefix: Prepended to each code in the manifest, e.g. ``"judge_"``.
    """
    got = {c.code: c for c in judgement.checks}
    out = []
    for code in expected:
        c = got.get(code)
        if c is None:
            out.append(CheckResult(code=prefix + code, passed=False, detail="judge skipped this"))
        else:
            out.append(CheckResult(code=prefix + code, passed=c.passed, detail=c.note))
    return out
