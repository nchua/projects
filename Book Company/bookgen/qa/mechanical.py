"""Manuscript mechanical checks (SPEC §6.3, §6.4): code, not models.

``check_manuscript`` runs every check and returns ``(checks, stats)``. A rule
that applies per spread emits one failing ``CheckResult`` per offending spread
(with ``spread`` set, so flags point at it), or one passing result if none fail.

Heuristics, documented so nobody mistakes them for NLP:
- adjectives come from the ``craft/adjectives.txt`` lexicon (no tagger);
- syllables are vowel groups with a silent-e rule (Flesch-Kincaid, §6.4);
- proper nouns (cast and family names, terms) are left out of readability stats;
- the §6.4 frequency-list share is not measured yet ``[VERIFY-6]``.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

from bookgen.craft import BandRule, load_adjectives, load_band_rules, load_banned_phrases
from bookgen.models import CheckResult, EpisodePlan, FamilyProfile, SeriesBible, SpreadText
from bookgen.qa import per_spread
from bookgen.textutil import count_words, sentences, words

_POSSESSIVE_RE = re.compile(r"['’]s$")
"""A trailing possessive, stripped before a token is compared with names."""


def _base(word: str) -> str:
    """``word`` without a trailing possessive (``Maya's`` -> ``Maya``)."""
    return _POSSESSIVE_RE.sub("", word)


PRONOUN_SETS: dict[str, frozenset[str]] = {
    "she/her": frozenset({"she", "her", "hers", "herself"}),
    "he/him": frozenset({"he", "him", "his", "himself"}),
}
"""Gendered pronoun sets the consistency check can own; they/them and it/its own none."""

GENERIC_PARENT_TERMS = frozenset(
    {"mom", "mommy", "mum", "mummy", "mother", "mama", "ma", "dad", "daddy", "father", "papa"}
    | {"pa", "appa", "umma", "eomma", "abba", "baba", "mamá", "papá", "amma", "ammi", "abbu"}
)
"""Words for a parent; any not in the family's own terms is flagged (§6.3)."""

NAME_SIMILARITY = 0.75
"""``difflib`` ratio above which a capitalised word is treated as a misspelt name."""


@dataclass(frozen=True)
class Names:
    """Who the text may name, and how (from the profile and the bible)."""

    exact: frozenset[str]
    """Every allowed name token, exact spelling (``Maya``, ``Toast``, ``Ferreira``)."""

    parent_terms: frozenset[str]
    """The family's own words for parents, lower-cased (``mama``, ``appa``)."""

    pronouns: dict[str, frozenset[str]]
    """Character id to the gendered pronouns that character owns."""

    @classmethod
    def build(cls, profile: FamilyProfile, bible: SeriesBible) -> Names:
        """Collect names from the profile and every bible cast member."""
        raw = [p.name for p in (*profile.parents, *profile.children, *profile.pets)]
        raw += [profile.companion_choice.name, *(c.name for c in bible.cast)]
        raw += [p.term for p in profile.parents]
        tokens = {t for name in raw for t in words(name) if t[:1].isupper() and len(t) > 2}
        pronouns = {c.id: PRONOUN_SETS.get(c.pronouns, frozenset()) for c in bible.cast}
        for person in (*profile.parents, *profile.children):
            pronouns[person.id] = PRONOUN_SETS.get(person.pronouns, frozenset())
        terms = frozenset(p.term.lower() for p in profile.parents)
        return cls(frozenset(tokens), terms, pronouns)


def _norm(text: str) -> str:
    """Lower-case and straighten quotes, for phrase matching."""
    return text.lower().replace("’", "'").replace("‘", "'")


@cache
def banned_phrase_patterns() -> list[tuple[str, re.Pattern[str]]]:
    """Compile ``craft/banned_phrases.txt``; ``...`` matches up to eight words in one sentence."""
    out = []
    for phrase in load_banned_phrases():
        parts = [re.escape(p.strip()) for p in re.split(r"\.\.\.|…", _norm(phrase))]
        gap = r"(?:[^\w.!?…]+\w+){0,8}?[^\w.!?…]+"  # never across a sentence end
        out.append((phrase, re.compile(r"\b" + gap.join(parts) + r"\b")))
    return out


def check_banned(spreads: list[SpreadText]) -> list[CheckResult]:
    """No banned phrase anywhere in the body text (§6.3)."""
    patterns = banned_phrase_patterns()
    failures = {}
    for s in spreads:
        hits = [phrase for phrase, rx in patterns if rx.search(_norm(s.text))]
        if hits:
            failures[s.spread] = f"banned phrase(s): {hits}"
    return per_spread("banned_phrases", failures)


def check_word_count(spreads: list[SpreadText], band: BandRule) -> CheckResult:
    """Total words within the band's range (§1.2)."""
    n = sum(count_words(s.text) for s in spreads)
    lo, hi = band.words_per_book
    return CheckResult(
        code="word_count_band",
        passed=lo <= n <= hi,
        detail=f"{n} words; band range {lo}-{hi}",
        value=n,
    )


def check_sentences(spreads: list[SpreadText], band: BandRule) -> list[CheckResult]:
    """Sentences per spread within range, and no sentence over the band's cap (§6.3)."""
    lo, hi = band.sentences_per_spread
    count_fail, cap_fail = {}, {}
    for s in spreads:
        sents = sentences(s.text)
        if not lo <= len(sents) <= hi:
            count_fail[s.spread] = f"{len(sents)} sentences; band range {lo}-{hi}"
        long = [x for x in sents if count_words(x) > band.max_words_per_sentence]
        if long:
            cap_fail[s.spread] = f"over {band.max_words_per_sentence} words: " + " | ".join(long)
    return [
        *per_spread("sentences_per_spread", count_fail),
        *per_spread("sentence_length", cap_fail),
    ]


def check_exclamations(spreads: list[SpreadText], cap: int) -> list[CheckResult]:
    """At most ``cap`` exclamation marks per spread (§6.3)."""
    failures = {
        s.spread: f"{s.text.count('!')} exclamation marks (max {cap})"
        for s in spreads
        if s.text.count("!") > cap
    }
    return per_spread("exclamations", failures)


def adjective_density(spreads: list[SpreadText], names: Names) -> float:
    """Lexicon adjectives per word across the book, names excluded."""
    lexicon = load_adjectives()
    ws = [w for s in spreads for w in words(s.text) if w not in names.exact]
    return sum(w.lower() in lexicon for w in ws) / max(len(ws), 1)


def check_names(spreads: list[SpreadText], names: Names) -> list[CheckResult]:
    """Names spelled exactly, never lower-cased; parent terms are the family's own (§6.3)."""
    exact_lower = {n.lower(): n for n in names.exact}
    failures: dict[int, str] = {}
    for s in spreads:
        problems = []
        for w in words(s.text):
            base = _base(w)
            if base in names.exact:
                continue
            if base.lower() in exact_lower and base != exact_lower[base.lower()]:
                problems.append(f"{w!r} should be {exact_lower[base.lower()]!r}")
            elif base.lower() in GENERIC_PARENT_TERMS and base.lower() not in names.parent_terms:
                problems.append(f"{w!r}: this family says {sorted(names.parent_terms)}")
            elif base[:1].isupper() and len(base) > 2:
                close = difflib.get_close_matches(base, names.exact, n=1, cutoff=NAME_SIMILARITY)
                if close:
                    problems.append(f"{w!r} looks like a misspelling of {close[0]!r}")
        if problems:
            failures[s.spread] = "; ".join(problems)
    return per_spread("names_exact", failures)


def check_pronouns(spreads: list[SpreadText], plan: EpisodePlan, names: Names) -> list[CheckResult]:
    """Gendered pronouns in a spread belong to someone present in that beat (§6.3)."""
    gendered = frozenset().union(*PRONOUN_SETS.values())
    failures = {}
    for s, beat in zip(spreads, plan.beats, strict=True):
        allowed = frozenset().union(*(names.pronouns.get(c, frozenset()) for c in beat.characters))
        used = {w.lower() for w in words(s.text)} & gendered
        stray = sorted(used - allowed)
        if stray:
            failures[s.spread] = f"{stray} but nobody present ({beat.characters}) uses them"
    return per_spread("pronouns", failures)


def syllables(word: str) -> int:
    """Vowel-group syllable estimate with a silent-e rule; at least 1."""
    w = word.lower().replace("'", "")
    groups = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and groups > 1:
        groups -= 1
    return max(groups, 1)


def readability(spreads: list[SpreadText], names: Names) -> dict[str, float]:
    """Flesch-Kincaid grade and mean sentence length, proper nouns excluded (§6.4)."""
    sents = [x for s in spreads for x in sentences(s.text)]
    ws = [w for x in sents for w in words(x) if _base(w) not in names.exact]
    if not ws or not sents:
        return {"fk_grade": 0.0, "mean_sentence_words": 0.0}
    syl = sum(syllables(w) for w in ws)
    wps = len(ws) / len(sents)
    fk = 0.39 * wps + 11.8 * (syl / len(ws)) - 15.59
    return {"fk_grade": round(fk, 2), "mean_sentence_words": round(wps, 2)}


def check_manuscript(
    spreads: list[SpreadText],
    plan: EpisodePlan,
    profile: FamilyProfile,
    bible: SeriesBible,
) -> tuple[list[CheckResult], dict[str, float]]:
    """Run every §6.3/§6.4 check; returns the checks and the stats for ``Manuscript.stats``."""
    rules = load_band_rules()
    band = rules.bands[profile.hero.band]
    names = Names.build(profile, bible)
    density = round(adjective_density(spreads, names), 3)
    stats = {**readability(spreads, names), "adjective_density": density}
    cap = rules.global_.max_adjectives_per_word
    checks = [
        check_word_count(spreads, band),
        *check_sentences(spreads, band),
        *check_banned(spreads),
        CheckResult(
            code="adjective_density",
            passed=density <= cap,
            detail=f"{density:.3f} adjectives per word (max {cap})",
            value=density,
        ),
        *check_exclamations(spreads, rules.global_.max_exclamations_per_spread),
        *check_names(spreads, names),
        *check_pronouns(spreads, plan, names),
        CheckResult(
            code="readability_fk",
            passed=stats["fk_grade"] <= band.max_fk_grade,
            detail=f"Flesch-Kincaid grade {stats['fk_grade']} (max {band.max_fk_grade})",
            value=stats["fk_grade"],
        ),
    ]
    return checks, stats


def failed(checks: Iterable[CheckResult]) -> list[CheckResult]:
    """The failing checks, for feeding back to the writer."""
    return [c for c in checks if not c.passed]
