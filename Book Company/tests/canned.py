"""Canned structured responses for the demo family (Maya, Toast the dragon, Pickles)."""

from __future__ import annotations

from collections.abc import Iterable

from bookgen.craft import load_rubric
from bookgen.models import (
    Beat,
    BriefCharacter,
    Briefs,
    CastMember,
    Critique,
    EpisodePlan,
    IllustrationBrief,
    JudgeCheck,
    Judgement,
    Location,
    ManuscriptDraft,
    RubricScore,
    Season,
    SeriesBible,
    SpreadText,
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


GOOD_SPREADS = [
    "Maya had a kite shaped like a fish. It had a long tail made of red ribbons. Toast "
    "wanted to fly it from the top of Windy Hill. There was one problem: Toast had never "
    "been to the top of a hill.",
    '"Today is the day," said Toast. He puffed out his round belly. Maya packed the fish '
    "kite, two pears and a ball of string. Then they set off up Puddle Lane.",
    "The hill was steep and the wind was strong. Toast flapped his small wings as hard as"
    " he could. He went up, up, up. Then he came down, bump, in a puddle.",
    'Maya looked at the muddy puddle, and then she looked at the fish kite. "Flapping is '
    'not working, so we need a new plan," she said. Toast blew a sad little spark into '
    "the puddle.",
    "At the allotment, the bean poles stood in rows. Maya had an idea. She tied the "
    'string to a pole and the kite to Toast. "Run," she said, and Toast ran.',
    "The kite went up and Toast went up too. For one whole second he was flying over the "
    "beans. Then the pole tipped over with a creak and a crash. Beans rolled all over the"
    " path, with Toast close behind.",
    "They walked on to the bottom of Windy Hill. The grass hissed in the wind. Toast sat "
    'on the bench with the wobbly leg. "I am not a flying dragon," he said.',
    "Maya sat down next to him. The bench went wibble, wobble. She watched the grass bend"
    " the same way, again and again. The wind was always pushing up the hill.",
    '"Toast, stop flapping," said Maya. "Open your wings and let the wind do the work." '
    "Toast did not think that would work at all, but he tried it anyway.",
    "Maya held the string and ran. Toast held the kite and opened his wings wide. The "
    "wind came up the hill. And this time it lifted them both, up to the very top.",
    "From the top they could see the yellow house. They could see Mr. Ferreira waving "
    "from the bakery. Toast was so happy that he hiccuped a shower of sparks.",
    "At home, Pickles sniffed the fish kite from nose to tail. Toast curled up by the "
    "back step and began to snore. Maya tied the kite to her bed. It was ready for the "
    "next windy day.",
]


def good_spreads() -> list[SpreadText]:
    """Twelve spreads that pass every mechanical check for band B."""
    return [SpreadText(spread=i, text=t) for i, t in enumerate(GOOD_SPREADS, start=1)]


def critique(score: int = 3, low: dict[str, int] | None = None) -> Critique:
    """A judge critique scoring every manuscript item ``score``, with ``low`` overrides."""
    low = low or {}
    items = [i for i in load_rubric().items if i.applies_to == "manuscript"]
    return Critique(
        scores=[
            RubricScore(
                key=i.key,
                score=low.get(i.key, score),
                fix_notes="" if low.get(i.key, score) == 3 else f"spread 4: tighten {i.key}",
            )
            for i in items
        ],
        summary="Tighten the middle.",
    )


def draft(spreads: list[SpreadText] | None = None) -> ManuscriptDraft:
    """A writer response; defaults to the good manuscript."""
    return ManuscriptDraft(spreads=spreads or good_spreads())


def demo_briefs(**overrides: object) -> Briefs:
    """Fifteen briefs that agree with ``demo_plan`` and the demo character folders."""
    plan = demo_plan()
    out = []
    for slot in [*range(1, 13), "cover", "recap", "teaser"]:
        beat = plan.beats[slot - 1] if isinstance(slot, int) else None
        chars = beat.characters if beat else ["maya", "toast"]
        where = beat.setting if beat else "the back step"
        out.append(
            IllustrationBrief(
                spread=slot,
                scene=f"Maya and Toast at {where}, the fish kite in hand",
                characters=[
                    BriefCharacter(id=c, pose="standing", expression="curious") for c in chars
                ],
                shot="medium",
                text_side=beat.text_side if beat else None,
                text_safe_area="open sky on the text side",
                palette_notes="late afternoon",
                negatives=["no lettering or readable text"],
            )
        )
    return Briefs.model_validate(
        {"episode": 1, "briefs": [b.model_dump() for b in out], **overrides}
    )
