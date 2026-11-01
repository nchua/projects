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
    CompanionEntry,
    ValueEntry,
    load_band_rules,
    load_companions,
    load_craft_guide,
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
    StyleBible,
    Value,
)
from bookgen.paths import SeriesPaths


def as_json(data: BaseModel | Any, **dump: Any) -> str:  # noqa: ANN401 - any JSON-able value
    """Render a model or plain data as compact, deterministic JSON for a prompt.

    Compact because indentation is pure input-token cost; deterministic (model field
    order, no sets) so a cached prefix stays byte-identical across calls.
    """
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json", **dump)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def writer_context(bible: SeriesBible) -> list[str]:
    """Craft Guide, then the bible: the cached prefix of every post-S3 call (§8.4)."""
    return [load_craft_guide(), as_json({"series_bible": bible.model_dump(mode="json")})]


def load_profile(paths: SeriesPaths) -> FamilyProfile:
    """``family/profile.json``."""
    return read_model(paths.profile, FamilyProfile)


def load_style(paths: SeriesPaths) -> StyleBible:
    """``series/style.json``: the locked style (D5)."""
    return read_model(paths.style, StyleBible)


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


def companion_entry(profile: FamilyProfile) -> CompanionEntry:
    """The catalog row for the family's companion archetype (D13)."""
    return next(c for c in load_companions() if c.id == profile.companion_choice.archetype)


def judge_checks(judgement: Judgement, codes: tuple[str, ...]) -> list[CheckResult]:
    """Map a judge's verdict onto ``judge_<code>`` checks; a code the judge skipped fails.

    ``codes`` mirrors the list in the judge's prompt file.
    """
    got = {c.code: c for c in judgement.checks}
    return [
        CheckResult(
            code=f"judge_{code}",
            passed=code in got and got[code].passed,
            detail=got[code].note if code in got else "judge skipped this",
            kind="judge",
        )
        for code in codes
    ]
