"""Pydantic data model for the pipeline (SPEC §8.5, Ledger §4.3).

Every artifact on disk under ``series/<series_id>/`` is one of these types
serialised as JSON. Stages read and write artifacts only through these models.
``Band``, ``Value``, ``Template`` and ``Companion`` are re-exported from
``bookgen.craft``, where they are built from the craft files.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bookgen.craft import Band as Band
from bookgen.craft import Companion as Companion
from bookgen.craft import Template as Template
from bookgen.craft import Value as Value
from bookgen.craft import load_rubric
from bookgen.textutil import count_words

Score = Annotated[int, Field(ge=0, le=3)]
"""A 0-3 score, as used by the rubric (§6.1) and image QA identity (S8)."""

SpreadNo = Annotated[int, Field(ge=1, le=12)]
"""A story spread number, 1-12 (§3.3 S4)."""

ImageSlot = SpreadNo | Literal["cover", "recap", "teaser"]
"""Which image: a story spread 1-12, or the cover, recap or teaser (§3.3 S6)."""

PersonId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
"""A stable lower-case id for a person or pet; also used as a folder name."""

TextSide = Literal["left", "right"]
"""Which side of a wide spread is reserved for text (D7)."""


class Model(BaseModel):
    """Base for all artifact models: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# --- Stages and manifest (§3.1, §8.5) -------------------------------------------------


class StageId(StrEnum):
    """Pipeline stage ids that write to an episode manifest (§3.2; S14 is Phase 3+)."""

    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"
    S6 = "S6"
    S7 = "S7"
    S8 = "S8"
    S9 = "S9"
    S10 = "S10"
    S11 = "S11"
    S12 = "S12"
    S13 = "S13"


class StageStatus(StrEnum):
    """Outcome of a stage run. ``flagged`` means a gate failed and wrote a flag (§3.1)."""

    STARTED = "started"
    DONE = "done"
    FLAGGED = "flagged"
    FAILED = "failed"


class CheckResult(Model):
    """One gate check's outcome, recorded whether it passed or not (§3.1, §3.2)."""

    code: str = Field(description="Short machine code, e.g. 'recap_length'.")
    passed: bool = Field(description="Whether the check passed.")
    detail: str = Field(default="", description="What was measured, or what failed and why.")
    spread: int | None = Field(default=None, description="Spread concerned, if specific.")
    value: float | None = Field(default=None, description="Measured number, if any.")


class StageRecord(Model):
    """The latest record of one stage in an episode manifest (§3.1)."""

    status: StageStatus = Field(description="Outcome of the most recent run.")
    model: str | None = Field(default=None, description="LLM model id used, if any.")
    provider: str | None = Field(default=None, description="Image provider used, if any.")
    cost_usd: float = Field(default=0.0, ge=0, description="Cumulative cost across attempts.")
    attempts: int = Field(default=1, ge=1, description="How many times the stage has run.")
    started: datetime = Field(description="UTC start of the most recent run.")
    finished: datetime | None = Field(default=None, description="UTC end of the most recent run.")
    checks: list[CheckResult] = Field(
        default_factory=list, description="Gate checks from the most recent run."
    )


class Flag(Model):
    """A failed gate the editor resolves with a manual control (§3.1)."""

    stage: StageId = Field(description="Stage whose gate failed.")
    code: str = Field(description="Short machine code, e.g. 'word_count_high'.")
    message: str = Field(description="What failed and the suggested manual fix.")
    spread: int | None = Field(default=None, description="Spread concerned, if specific.")
    created: datetime = Field(description="UTC time the flag was raised.")
    resolved: bool = Field(default=False, description="Set when the editor has dealt with it.")


class Manifest(Model):
    """Per-episode run record, ``epNN/manifest.json`` (§3.1, §3.4)."""

    episode: int = Field(ge=1, description="Episode number.")
    stages: dict[StageId, StageRecord] = Field(
        default_factory=dict, description="Latest record per stage."
    )
    flags: list[Flag] = Field(default_factory=list, description="Flags raised by gates.")


# --- Family intake (S0) -----------------------------------------------------------------


class ParentProfile(Model):
    """A parent or carer who may appear as a cameo (§5.5)."""

    id: PersonId = Field(description="Stable person id.")
    name: str = Field(description="Given name, spelled exactly as the family writes it.")
    term: str = Field(description="What the child calls them ('Mama', 'Appa'); used verbatim.")
    pronouns: str = Field(description="Pronouns, e.g. 'she/her'.")


class ChildProfile(Model):
    """A child reader and hero (§8.5)."""

    id: PersonId = Field(description="Stable person id.")
    name: str = Field(description="Given name, spelled exactly as the family writes it (§6.3).")
    pronouns: str = Field(description="Pronouns, e.g. 'she/her'; checked for consistency.")
    birth_month: str = Field(
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM; month only, never full DOB."
    )
    band: Band = Field(description="Reader band (§1.2); Phase 0 builds band B only.")


class PetProfile(Model):
    """A family pet that may appear as a cameo (§5.5)."""

    id: PersonId = Field(description="Stable id.")
    name: str = Field(description="Pet's name.")
    species: str = Field(description="Species, e.g. 'dog'.")
    description: str = Field(description="Breed, colouring and one distinctive trait.")


class CompanionChoice(Model):
    """The child's companion pick at intake (D13)."""

    archetype: Companion = Field(description="Archetype id from craft/companions.yaml.")
    name: str = Field(description="The name the child gave it.")
    colour: str = Field(description="The child's colour choice, fed to the companion sheet (S2).")


class ConsentFlags(Model):
    """What the parent has agreed to (§7.2, §7.3). Defaults are the most private choice."""

    personalized_story: bool = Field(description="Use the child's name and details in stories.")
    likeness_from_photos: bool = Field(default=False, description="Photos may be processed (L2).")
    retain_photos: bool = Field(default=False, description="Keep photos after S2 (D2: no).")
    family_cameos: bool = Field(default=False, description="Parents and pets may appear (L3).")


class Hair(Model):
    """Hair fields of an appearance card (§5.2)."""

    colour: str = Field(description="Hair colour, e.g. 'black', 'auburn'.")
    texture: str = Field(description="Texture, e.g. 'straight', 'wavy', 'coily'.")
    length: str = Field(description="Length, e.g. 'chin-length', 'shoulder', 'short'.")
    style: str = Field(description="Usual style, e.g. 'two puffs', 'bob with fringe'.")


class AppearanceCard(Model):
    """Structured likeness for one person (§5.2); the only route into image prompts."""

    person_id: str = Field(description="Id of the person in the family profile.")
    hair: Hair = Field(description="Hair colour, texture, length and style.")
    skin_tone_id: int = Field(ge=1, le=10, description="Swatch id from the fixed palette.")
    eyes: str = Field(description="Eye colour and shape notes.")
    glasses: bool = Field(default=False, description="Wears glasses.")
    assistive_devices: list[str] = Field(
        default_factory=list, description="Hearing aids, mobility aids and similar."
    )
    features: list[str] = Field(default_factory=list, description="Distinctive features.")
    signature_outfit: str = Field(description="The outfit the parent picked (S1 gate).")
    outfit_suggestions: list[str] = Field(
        default_factory=list, max_length=3, description="S1's three suggestions, kept for the edit."
    )
    height_class: Literal["smaller", "same", "taller"] = Field(
        description="Height relative to the companion."
    )


class FamilyProfile(Model):
    """Validated intake form, ``family/profile.json`` (S0, §8.5)."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$", description="Family id; default series id.")
    parents: list[ParentProfile] = Field(default_factory=list, description="Parents and carers.")
    children: list[ChildProfile] = Field(min_length=1, description="Children; the first is hero.")
    pets: list[PetProfile] = Field(default_factory=list, description="Pets.")
    companion_choice: CompanionChoice = Field(description="Companion archetype, name and colour.")
    value_priorities: list[Value] = Field(
        min_length=1, description="Values the parents want, most important first."
    )
    exclusions: list[str] = Field(
        default_factory=list, description="Topics never to include; feeds the bible's forbidden."
    )
    locale: str = Field(default="en-US", description="BCP 47 locale; English only [OPEN-5].")
    consent: ConsentFlags = Field(description="Consent flags.")
    appearance_cards: list[AppearanceCard] = Field(
        default_factory=list,
        description="Phase 0 L1 only: hand-written cards. S0 moves each to "
        "characters/<id>/appearance.json; they are not kept in profile.json.",
    )

    @model_validator(mode="after")
    def _check_ids(self) -> Self:
        """Ids are unique (companion included), priorities don't repeat, cards are known."""
        ids = self.person_ids
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate person ids: {sorted(dupes)}")
        if not self.companion_id or self.companion_id in ids:
            raise ValueError(f"companion name {self.companion_choice.name!r} clashes or is empty")
        if len(set(self.value_priorities)) != len(self.value_priorities):
            raise ValueError("value_priorities must not repeat")
        unknown = {c.person_id for c in self.appearance_cards} - set(ids)
        if unknown:
            raise ValueError(f"appearance cards for unknown people: {sorted(unknown)}")
        return self

    @property
    def hero(self) -> ChildProfile:
        """The series hero: the first child (one series per child, [OPEN-4])."""
        return self.children[0]

    @property
    def person_ids(self) -> list[str]:
        """Ids of every parent, child and pet, in that order."""
        return [p.id for p in (*self.parents, *self.children, *self.pets)]

    @property
    def companion_id(self) -> str:
        """Character id for the companion: its given name, slugged ('Toast' -> 'toast')."""
        return re.sub(r"[^a-z0-9]+", "_", self.companion_choice.name.lower()).strip("_")

    @property
    def character_ids(self) -> list[str]:
        """Who gets a ``characters/<id>/`` folder: children, companion, consented cameos."""
        ids = [c.id for c in self.children] + [self.companion_id]
        if self.consent.family_cameos:
            ids += [p.id for p in (*self.parents, *self.pets)]
        return ids


# --- Characters and style (S1-S3) -------------------------------------------------------


class SheetPaths(Model):
    """Paths to the turnaround views of a chosen character sheet (S2)."""

    front: Path = Field(description="Front view crop.")
    three_quarter: Path = Field(description="Three-quarter view crop.")
    side: Path = Field(description="Side view crop.")
    expressions: list[Path] = Field(default_factory=list, description="Four expression crops.")


class CharacterSheet(Model):
    """The approved turnaround sheet every later image references (D2, S2)."""

    person_id: str = Field(description="Person or companion id.")
    style_id: str = Field(description="Style the sheet was drawn in.")
    paths: SheetPaths = Field(description="Crops used for reference passing.")
    provider: str = Field(description="Image provider that drew it.")
    model: str = Field(description="Provider model id.")
    seed: int | None = Field(default=None, description="Seed, if the provider exposes one.")
    approved_at: datetime | None = Field(default=None, description="When the parent picked it.")


class StyleBible(Model):
    """A locked illustration style (D5); ``craft/style_bibles/<id>.yaml``, ``series/style.json``."""

    id: str = Field(description="Style id, e.g. 'gouache-warm'.")
    name: str = Field(description="Human-readable name.")
    attributes: list[str] = Field(min_length=1, description="Named style attributes.")
    palette: list[str] = Field(min_length=1, description="Hex colours.")
    line: str = Field(description="Line treatment.")
    lighting: str = Field(description="Lighting treatment.")
    anchor_images: list[Path] = Field(default_factory=list, description="3-5 anchors (S3).")
    provider: str | None = Field(default=None, description="Pinned provider after the bake-off.")
    model: str | None = Field(default=None, description="Pinned model after the bake-off.")
    pinned_at: datetime | None = Field(default=None, description="When provider/model were pinned.")


class Location(Model):
    """A place in the series world (S3)."""

    name: str = Field(description="Location name.")
    description: str = Field(description="One-line description with a sensory signature.")
    is_home: bool = Field(
        default=False, description="The hero's home ground; exempt from the no-repeat rule (§4.4)."
    )


class World(Model):
    """The series world (S3)."""

    name: str = Field(description="World name.")
    locations: list[Location] = Field(min_length=5, max_length=8, description="5-8 locations.")


class CastMember(Model):
    """A recurring character in the series bible (S3)."""

    id: PersonId = Field(description="Character id; matches a person id for family members.")
    name: str = Field(description="Name, spelled exactly.")
    role: Literal["hero", "companion", "side", "cameo"] = Field(description="Role in the series.")
    pronouns: str = Field(description="Pronouns, e.g. 'she/her', 'he/him', 'they/them', 'it/its'.")
    description: str = Field(description="Personality, voice and one visual anchor.")


class Season(Model):
    """The six-episode season arc (§4.2, S3)."""

    goal: str = Field(description="What the season builds toward.")
    loglines: list[str] = Field(min_length=6, max_length=6, description="Six episode loglines.")
    finale: str = Field(description="Shape of the finale.")


class SeriesBible(Model):
    """``series/bible.json`` (S3)."""

    series_id: str = Field(description="Series id.")
    world: World = Field(description="World name and locations.")
    cast: list[CastMember] = Field(min_length=2, description="Hero, companion, side cast, cameos.")
    tone: str = Field(description="Tone and humour register.")
    naming: str = Field(description="Naming conventions for new characters and places.")
    season: Season = Field(description="Season goal, loglines and finale.")
    forbidden: list[str] = Field(default_factory=list, description="From parent exclusions.")
    style_id: str = Field(description="Locked style id (D5).")


# --- Ledger (§4.3) -----------------------------------------------------------------------


class LedgerFact(Model):
    """An established world rule or name."""

    text: str = Field(description="The fact, stated plainly.")
    episode: int = Field(ge=1, description="Episode that established it.")


class CastState(Model):
    """Continuity state for one character."""

    character_id: str = Field(description="Cast member id.")
    appearance_ref: str = Field(description="Path or id of the sheet that defines the look.")
    voice_tics: list[str] = Field(default_factory=list, description="Stable verbal habits.")
    relationship: str = Field(description="Relationship to the hero.")
    last_seen: int = Field(ge=1, description="Last episode the character appeared in.")


class LedgerObject(Model):
    """A named prop and where it is now."""

    name: str = Field(description="Prop name, e.g. 'the brass lantern'.")
    location: str = Field(description="Where it is at the end of the last episode.")
    introduced: int = Field(ge=1, description="Episode that introduced it.")


class RunningGag(Model):
    """A running gag with a usage count, so the planner reuses it sparingly."""

    description: str = Field(description="The gag.")
    uses: int = Field(default=0, ge=0, description="Times used so far.")


class LessonCovered(Model):
    """A value already used, so it does not repeat within a season (§4.4)."""

    episode: int = Field(ge=1, description="Episode number.")
    value: Value = Field(description="Value covered.")


class OpenThread(Model):
    """An unresolved hook the planner may pick up."""

    description: str = Field(description="The hook.")
    opened_in: int = Field(ge=1, description="Episode that opened it.")


class Ledger(Model):
    """``series/ledger.json``: the continuity ledger (§4.3), updated by S13."""

    facts: list[LedgerFact] = Field(default_factory=list, description="World rules and names.")
    cast_state: list[CastState] = Field(default_factory=list, description="Per-character state.")
    locations_visited: list[str] = Field(default_factory=list, description="Locations, in order.")
    objects: list[LedgerObject] = Field(default_factory=list, description="Named props.")
    running_gags: list[RunningGag] = Field(default_factory=list, description="Gags with counts.")
    lessons_covered: list[LessonCovered] = Field(default_factory=list, description="Values used.")
    open_threads: list[OpenThread] = Field(default_factory=list, description="Unresolved hooks.")
    last_summary: str = Field(default="", description="<= 120 words; feeds the recap spread.")
    next_hook: str = Field(default="", description="One line; feeds the teaser and next plan.")
    child_age_at_last: int | None = Field(
        default=None, ge=0, description="Child's age at the last episode; drives band refresh."
    )


# --- Episode text (S4-S5) ----------------------------------------------------------------


class Beat(Model):
    """One spread of the episode plan (S4)."""

    spread: SpreadNo = Field(description="Spread number, 1-12.")
    setting: str = Field(description="Location name from the bible.")
    characters: list[str] = Field(min_length=1, description="Ids of characters present.")
    action: str = Field(description="The one picturable action.")
    emotion: str = Field(description="Emotional beat.")
    hook: str = Field(description="Page-turn hook into the next spread.")
    text_side: TextSide = Field(description="Side reserved for text (D7).")


class EpisodePlan(Model):
    """``epNN/plan.json`` (S4)."""

    episode: int = Field(ge=1, description="Episode number.")
    title: str = Field(description="Episode title.")
    logline: str = Field(description="One-sentence logline.")
    value: Value = Field(description="Value for this episode.")
    pattern: list[str] = Field(min_length=2, description="The value's pattern from the catalog.")
    template: Template = Field(description="Structure template (§4.4).")
    beats: list[Beat] = Field(min_length=12, max_length=12, description="12 beats, spreads 1-12.")
    value_lands_at: SpreadNo = Field(description="Spread where the value lands (9-11; QA flag).")
    recap: str = Field(description="Recap text, <= 60 words (§4.5, QA flag); outside the 12.")
    teaser: str = Field(description="Teaser spread text.")
    grownup_questions: list[str] = Field(
        min_length=3, max_length=3, description="Three questions for the grown-up reader."
    )

    @model_validator(mode="after")
    def _beats_in_order(self) -> Self:
        """Beats cover spreads 1-12 exactly once, in order (word limits are QA flags)."""
        if [b.spread for b in self.beats] != list(range(1, 13)):
            raise ValueError("beats must be spreads 1..12 in order")
        return self


class SpreadText(Model):
    """Text for one spread (S5)."""

    spread: SpreadNo = Field(description="Spread number, 1-12.")
    text: str = Field(description="Body text, exactly as typeset.")
    read_aloud_notes: str = Field(default="", description="Emphasis and sound-word notes.")


class Manuscript(Model):
    """``epNN/manuscript.json`` (S5); the editor edits ``text`` here in S12."""

    episode: int = Field(ge=1, description="Episode number.")
    spreads: list[SpreadText] = Field(
        min_length=12, max_length=12, description="Text per spread, spreads 1-12 in order."
    )
    word_count: int = Field(default=0, ge=0, description="Total body words; derived on load.")
    stats: dict[str, float] = Field(
        default_factory=dict, description="Mechanical-check measurements (§6.3, §6.4)."
    )

    @model_validator(mode="before")
    @classmethod
    def _derive_word_count(cls, data: Any) -> Any:  # noqa: ANN401 - raw input before validation
        """``word_count`` is always recomputed from the spreads, never trusted from disk."""
        if isinstance(data, dict) and isinstance(data.get("spreads"), list):
            spreads = data["spreads"]
            texts = (s.text if isinstance(s, SpreadText) else s.get("text", "") for s in spreads)
            data = {**data, "word_count": sum(count_words(t) for t in texts)}
        return data

    @model_validator(mode="after")
    def _spreads_in_order(self) -> Self:
        """Spreads are 1..12 in order, so the editor can't reorder text by accident."""
        if [s.spread for s in self.spreads] != list(range(1, 13)):
            raise ValueError("manuscript spreads must be 1..12 in order")
        return self


class ManuscriptDraft(Model):
    """What the writer returns (S5): just the twelve spreads, nothing about its reasoning."""

    spreads: list[SpreadText] = Field(
        min_length=12,
        max_length=12,
        description="Spreads 1-12 in order: text and read-aloud notes.",
    )


class RubricScore(Model):
    """One rubric item as the S5 judge scored it (§6.1, §6.2)."""

    key: str = Field(description="Rubric item key from craft/judge_rubric.yaml.")
    score: Score = Field(description="0-3 against the item's anchors.")
    fix_notes: str = Field(description="Specific, actionable notes naming spreads; '' if 3.")


class Critique(Model):
    """The S5 judge's verdict on one draft."""

    scores: list[RubricScore] = Field(description="One entry per manuscript rubric item.")
    summary: str = Field(description="The two or three changes that matter most.")


class CritiqueRound(Model):
    """One judge pass in the S5 loop, with the mechanical failures it was paired with."""

    round: int = Field(ge=0, description="0 scores the first draft; n scores revision n.")
    critique: Critique = Field(description="The judge's scores and notes.")
    mechanical_failures: list[CheckResult] = Field(
        default_factory=list, description="Mechanical checks that failed on this draft."
    )


class CritiqueLog(Model):
    """``epNN/critique.json``: every judge round of S5, for the editor and evals."""

    episode: int = Field(ge=1, description="Episode number.")
    rounds: list[CritiqueRound] = Field(default_factory=list, description="In order.")


# --- Illustration (S6-S8) ----------------------------------------------------------------


class BriefCharacter(Model):
    """A character's placement in one illustration brief."""

    id: str = Field(description="Character id; must have a sheet (S6 gate).")
    pose: str = Field(description="Pose, in concrete terms.")
    expression: str = Field(description="Expression, matching the beat's emotion.")


class IllustrationBrief(Model):
    """One entry of ``epNN/briefs.json`` (S6)."""

    spread: ImageSlot = Field(description="Story spread 1-12, or a cover/recap/teaser image.")
    scene: str = Field(description="Scene in concrete nouns.")
    characters: list[BriefCharacter] = Field(default_factory=list, description="Who is in it.")
    shot: Literal["wide", "medium", "close"] = Field(description="Shot distance.")
    text_side: TextSide | None = Field(
        default=None, description="Story spreads: the plan's text side (S6 gate). None otherwise."
    )
    text_safe_area: str = Field(description="Where text sits, described for the illustrator.")
    palette_notes: str = Field(description="Palette and time of day.")
    continuity_props: list[str] = Field(default_factory=list, description="Props from the ledger.")
    negatives: list[str] = Field(default_factory=list, description="Things that must not appear.")


class Briefs(Model):
    """``epNN/briefs.json`` (S6): spreads 1-12 plus cover, recap and teaser."""

    episode: int = Field(default=1, ge=1, description="Episode number (set by code).")
    briefs: list[IllustrationBrief] = Field(min_length=1, description="One brief per image slot.")


class QAResult(Model):
    """Vision judge scores for one image candidate (S8)."""

    identity: dict[str, Score] = Field(default_factory=dict, description="Char id to 0-3 match.")
    count_ok: bool = Field(description="Correct number of characters.")
    expression_ok: bool = Field(description="Expressions match the beat.")
    no_text: bool = Field(description="No letters or text in the image (D4).")
    anatomy_ok: bool = Field(description="Hands, eyes and limbs are correct.")
    text_area_quiet: bool = Field(description="The text-safe area is actually quiet.")
    safe: bool = Field(description="Nothing scary or inappropriate for the band.")
    gutter_ok: bool = Field(description="No face across the gutter line.")
    notes: str = Field(default="", description="Fix notes folded into a regeneration prompt.")


class ImageCandidate(Model):
    """One generated image candidate, ``epNN/images/sNN_cK.png`` (S7)."""

    spread: ImageSlot = Field(description="Which image.")
    k: int = Field(ge=1, description="Candidate index.")
    path: Path = Field(description="Image file path.")
    provider: str = Field(description="Image provider.")
    model: str = Field(description="Provider model id.")
    seed: int | None = Field(default=None, description="Seed, if exposed.")
    prompt_hash: str = Field(description="Hash of the rendered prompt (§3.1).")
    qa: QAResult | None = Field(default=None, description="Filled by S8.")


# --- Judge outputs (S3-S5) ---------------------------------------------------------------


class JudgeCheck(Model):
    """One named check from a model judge; the stage turns it into a ``CheckResult``."""

    code: str = Field(description="The check code named in the judge prompt.")
    passed: bool = Field(description="Whether the artifact passes this check.")
    note: str = Field(description="Specific evidence; for a failure, what to change.")


class Judgement(Model):
    """A judge call's verdict: one entry per check code the prompt lists."""

    checks: list[JudgeCheck] = Field(description="One entry per requested check code.")


# --- Review (S12) ------------------------------------------------------------------------


class Review(Model):
    """The editor's rubric scores and approval (S12)."""

    episode: int = Field(ge=1, description="Episode number.")
    scores: dict[str, Score] = Field(description="Rubric item key to 0-3 score.")
    edits: list[str] = Field(default_factory=list, description="Summary of edits made.")
    approved_by: str | None = Field(default=None, description="Editor who approved.")
    approved_at: datetime | None = Field(default=None, description="When it was approved.")

    @model_validator(mode="after")
    def _known_items(self) -> Self:
        """Score keys are rubric item keys from ``craft/judge_rubric.yaml``."""
        unknown = set(self.scores) - {i.key for i in load_rubric().items}
        if unknown:
            raise ValueError(f"unknown rubric items: {sorted(unknown)}")
        return self
