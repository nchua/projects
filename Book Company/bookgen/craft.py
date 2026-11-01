"""Craft asset loaders and the enums built from them (SPEC §8.8).

The craft files are the single source of truth for bands, values, structure
templates and companion archetypes. The ``Band``, ``Value``, ``Template`` and
``Companion`` enums are generated from those files at import time, so adding
a value or companion is one YAML entry and no code change.

Seam: every reader of ``craft/`` goes through this module. Stages never open
craft files directly.
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
"""Repository root for the Book Company project (the folder holding SPEC.md)."""

CRAFT_DIR: Path = Path(os.environ.get("BOOKGEN_CRAFT_DIR", str(PROJECT_ROOT / "craft")))
"""Directory holding the versioned craft assets; override with ``BOOKGEN_CRAFT_DIR``."""


class _CraftModel(BaseModel):
    """Base for craft entries: unknown keys are rejected so typos fail loudly."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ValueEntry(_CraftModel):
    """One row of the values catalog (SPEC §1.5)."""

    id: str = Field(description="Stable id used by the Value enum and the CLI `--value` flag.")
    name: str = Field(description="Human-readable name, as in §1.5.")
    pattern: list[str] = Field(min_length=2, description="Story pattern steps, in order.")
    shown_not_told: str = Field(description="The test the judge applies for rubric item 5.")


class TemplateBeat(_CraftModel):
    """One beat of a structure template, mapped onto a spread range."""

    name: str = Field(description="Short beat name, e.g. 'three obstacles'.")
    spreads: tuple[int, int] = Field(description="Inclusive suggested spread range, 1-12.")
    note: str = Field(description="Guidance for the planner on what the beat must do.")


class TemplateEntry(_CraftModel):
    """A structure template the episode plan rotates through (SPEC §4.4)."""

    id: str = Field(description="Stable id used by the Template enum.")
    name: str = Field(description="Human-readable template name.")
    summary: str = Field(description="One-line description of the story shape.")
    beats: list[TemplateBeat] = Field(min_length=3, max_length=5, description="3-5 beats.")


class BandRule(_CraftModel):
    """Numeric and qualitative rules for one reader band (SPEC §1.2)."""

    age: tuple[int, int] = Field(description="Inclusive age range in years.")
    words_per_book: tuple[int, int] = Field(description="Inclusive word-count range per book.")
    sentences_per_spread: tuple[int, int] = Field(description="Inclusive sentences per spread.")
    max_words_per_sentence: int = Field(gt=0, description="Sentence length cap (§6.3).")
    dialogue: Literal["none", "light"] = Field(description="How much dialogue the band allows.")
    scare_level: Literal["none", "mild", "moderate"] = Field(description="Maximum scare level.")
    body_pt: tuple[int, int] = Field(description="Body text size range in points (S10).")
    traits: list[str] = Field(description="Signature craft traits for the band.")
    phase0: bool = Field(description="Whether the band is built in Phase 0.")


class BandGlobals(_CraftModel):
    """Rules shared by every band (SPEC §6.3)."""

    spreads_per_book: int = Field(description="Story spreads per book.")
    max_adjectives_per_word: float = Field(description="Adjective density cap.")
    max_exclamations_per_spread: int = Field(description="Exclamation mark cap per spread.")


class BandRules(_CraftModel):
    """The whole of ``band_rules.yaml``."""

    version: int = Field(description="Craft file version.")
    global_: BandGlobals = Field(alias="global", description="Rules shared by every band.")
    bands: dict[str, BandRule] = Field(description="Band key (A/B/C) to its rules.")


class CompanionEntry(_CraftModel):
    """A companion archetype the child can pick at intake (SPEC D13)."""

    id: str = Field(description="Stable id used by the Companion enum and `--companion`.")
    name: str = Field(description="Human-readable archetype name.")
    silhouette: str = Field(description="Shape language the character sheet starts from.")
    scale: str = Field(description="Size relative to the hero.")
    voice: str = Field(description="How it talks; supplies the book's second voice.")
    skill: str = Field(description="What it contributes in teamwork stories.")
    flaw: str = Field(description="What stops it solving the story alone.")
    running_gag_seed: str = Field(description="A starting running gag for the ledger.")


class RubricItem(_CraftModel):
    """One judge rubric item with 0-3 anchors (SPEC §6.1)."""

    id: int = Field(ge=1, description="Item number as in §6.1.")
    key: str = Field(description="Snake-case key used in score dicts.")
    name: str = Field(description="Human-readable item name.")
    applies_to: Literal["manuscript", "illustration"] = Field(description="What gets scored.")
    anchors: dict[int, str] = Field(description="Score (0-3) to what that score looks like.")


class PassRule(_CraftModel):
    """Rubric pass rule (SPEC §6.1)."""

    min_item_score: int = Field(description="Lowest allowed score on any item.")
    min_mean: float = Field(description="Lowest allowed mean across items.")


class JudgeRubric(_CraftModel):
    """The whole of ``judge_rubric.yaml``."""

    version: int = Field(description="Craft file version.")
    pass_rule: PassRule = Field(description="Pass rule for a book.")
    items: list[RubricItem] = Field(description="Rubric items in §6.1 order.")


def _load_yaml(relative: str) -> Any:  # noqa: ANN401 - YAML is untyped until validated
    """Read one YAML file under ``CRAFT_DIR``."""
    with (CRAFT_DIR / relative).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@cache
def load_values() -> list[ValueEntry]:
    """Return the values catalog (§1.5)."""
    return [ValueEntry.model_validate(v) for v in _load_yaml("values_catalog.yaml")["values"]]


@cache
def load_templates() -> list[TemplateEntry]:
    """Return the structure templates (§4.4)."""
    raw = _load_yaml("structure_templates.yaml")["templates"]
    return [TemplateEntry.model_validate(t) for t in raw]


@cache
def load_band_rules() -> BandRules:
    """Return the band rules (§1.2)."""
    return BandRules.model_validate(_load_yaml("band_rules.yaml"))


@cache
def load_companions() -> list[CompanionEntry]:
    """Return the companion archetypes (D13)."""
    return [CompanionEntry.model_validate(c) for c in _load_yaml("companions.yaml")["companions"]]


@cache
def load_rubric() -> JudgeRubric:
    """Return the judge rubric (§6.1)."""
    return JudgeRubric.model_validate(_load_yaml("judge_rubric.yaml"))


def load_banned_phrases() -> list[str]:
    """Return banned phrases (§6.3), lower-cased, comments and blanks dropped."""
    text = (CRAFT_DIR / "banned_phrases.txt").read_text(encoding="utf-8")
    return [ln.strip().lower() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]


def style_bible_path(style_id: str) -> Path:
    """Return the path of a style bible by id (``craft/style_bibles/<id>.yaml``)."""
    return CRAFT_DIR / "style_bibles" / f"{style_id}.yaml"


def load_style_bible_raw(style_id: str) -> dict[str, Any]:
    """Return a style bible's raw mapping; validate with ``models.StyleBible``."""
    path = style_bible_path(style_id)
    if not path.exists():
        available = sorted(p.stem for p in path.parent.glob("*.yaml"))
        raise FileNotFoundError(f"unknown style {style_id!r}; available: {available}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _enum(name: str, ids: list[str]) -> type[StrEnum]:
    """Build a StrEnum whose member names are upper-cased ids and values are the ids."""
    return StrEnum(name, {i.upper().replace("-", "_"): i for i in ids})  # type: ignore[return-value]


Band = _enum("Band", list(load_band_rules().bands))
"""Reader band (A/B/C), built from ``band_rules.yaml``."""

Value = _enum("Value", [v.id for v in load_values()])
"""Story value, built from ``values_catalog.yaml``."""

Template = _enum("Template", [t.id for t in load_templates()])
"""Structure template, built from ``structure_templates.yaml``."""

Companion = _enum("Companion", [c.id for c in load_companions()])
"""Companion archetype, built from ``companions.yaml``."""
