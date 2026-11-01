"""Canned structured responses for the demo family (Maya, Toast the dragon, Pickles)."""

from __future__ import annotations

from collections.abc import Iterable

from bookgen.models import (
    Beat,
    CastMember,
    EpisodePlan,
    JudgeCheck,
    Judgement,
    Location,
    Season,
    SeriesBible,
    World,
)

HOME = "the yellow house"
LOCATIONS = [
    (HOME, "Maya's home; the back step creaks and smells of rain on brick.", True),
    ("Puddle Lane", "A sloping lane where every puddle has a name.", False),
    ("Mr. Ferreira's bakery", "Warm toast smell and a bell that sticks.", False),
    ("the allotment", "Bean poles, wet soil, a scarecrow with one mitten.", False),
    ("Windy Hill", "Grass that hisses and a bench with a wobbly leg.", False),
]


def demo_bible(**update: object) -> SeriesBible:
    """A valid bible for the demo family; ``update`` overrides top-level fields."""
    bible = SeriesBible(
        series_id="anything",
        world=World(
            name="Puddle Lane",
            locations=[Location(name=n, description=d, is_home=h) for n, d, h in LOCATIONS],
        ),
        cast=[
            CastMember(
                id="maya",
                name="Maya",
                role="hero",
                pronouns="she/her",
                description="Asks why, tests everything. Round red glasses.",
            ),
            CastMember(
                id="toast",
                name="Toast",
                role="companion",
                pronouns="he/him",
                description="Teal dragon, announces everything grandly, hiccups sparks.",
            ),
            CastMember(
                id="mr_ferreira",
                name="Mr. Ferreira",
                role="side",
                pronouns="he/him",
                description="Baker who hums opera; flour on his eyebrows.",
            ),
            CastMember(
                id="pickles",
                name="Pickles",
                role="cameo",
                pronouns="he/him",
                description="Scruffy terrier; one white ear that never stands up.",
            ),
            CastMember(
                id="dana",
                name="Dana",
                role="cameo",
                pronouns="she/her",
                description="Mama; laughs with her whole face.",
            ),
        ],
        tone="Warm, dry humour; mild weather-scale peril at most.",
        naming="Places named for what they sound like; people by family name.",
        season=Season(
            goal="Toast learns to fly to the top of Windy Hill.",
            loglines=[f"logline {i}" for i in range(1, 7)],
            finale="Toast flies Maya's kite to the top of the hill.",
        ),
        forbidden=["dragons breathing fire on people"],
        style_id="whatever",
    )
    return SeriesBible.model_validate({**bible.model_dump(), **update})


SETTINGS = [HOME, HOME, "Puddle Lane", "Puddle Lane", "the allotment", "the allotment"]
SETTINGS += ["Windy Hill", "Windy Hill", "Windy Hill", "Windy Hill", "Windy Hill", HOME]


def demo_plan(**update: object) -> EpisodePlan:
    """A valid 12-beat perseverance plan; ``update`` overrides top-level fields."""
    beats = [
        Beat(
            spread=n,
            setting=SETTINGS[n - 1],
            characters=["maya", "toast"] if n != 12 else ["maya", "toast", "pickles"],
            action=f"action {n}",
            emotion=f"emotion {n}",
            hook=f"hook {n}",
            text_side="left" if n % 2 else "right",
        )
        for n in range(1, 13)
    ]
    plan = EpisodePlan(
        episode=1,
        title="Toast and the Very Tall Hill",
        logline="Maya helps Toast reach the top of Windy Hill.",
        value="perseverance",
        pattern=["try", "fail", "change approach", "try again (three attempts in all)"],
        template="quest",
        beats=beats,
        value_lands_at=10,
        recap="Welcome to Puddle Lane, where Maya lives with a dragon called Toast.",
        teaser="Next time: a letter with no stamp.",
        grownup_questions=["What would you try?", "When did you change your plan?", "Why?"],
    )
    return EpisodePlan.model_validate({**plan.model_dump(), **update})


def judgement(codes: Iterable[str], failing: Iterable[str] = ()) -> Judgement:
    """A judge verdict answering ``codes``, with ``failing`` ones marked failed."""
    bad = set(failing)
    return Judgement(
        checks=[
            JudgeCheck(code=c, passed=c not in bad, note="fix spread 4" if c in bad else "ok")
            for c in codes
        ]
    )
