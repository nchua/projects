"""Word and sentence tokenising, and the manuscript fields derived from it."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bookgen.models import Manuscript
from bookgen.textutil import count_words, sentences


def test_words_keep_contractions_and_hyphens() -> None:
    """Contractions and inner hyphens are one word each; punctuation is not a word."""
    assert count_words("Don't wake the half-asleep dragon… *Tap. Tap.*") == 7


def test_sentences_split_on_terminals_but_not_dialogue_tags() -> None:
    """A capital after the terminal starts a sentence; a dialogue tag does not."""
    text = '"Wait!" said Maya. Toast hopped. Was it working? No… It was not.'
    assert sentences(text) == [
        '"Wait!" said Maya.',
        "Toast hopped.",
        "Was it working?",
        "No…",
        "It was not.",
    ]


def _ms(texts: list[str]) -> dict[str, object]:
    """A manuscript payload with one spread per text."""
    return {
        "episode": 1,
        "word_count": 9999,
        "spreads": [{"spread": i, "text": t} for i, t in enumerate(texts, start=1)],
    }


def test_manuscript_word_count_is_derived() -> None:
    """A stored word_count is ignored and recomputed from the text."""
    ms = Manuscript.model_validate(_ms(["One two three."] * 12))
    assert ms.word_count == 36
    assert Manuscript.model_validate_json(ms.model_dump_json()).word_count == 36


def test_manuscript_spreads_must_be_in_order() -> None:
    """Twelve spreads, 1..12 in order."""
    payload = _ms(["a"] * 12)
    spreads = payload["spreads"]
    assert isinstance(spreads, list)
    with pytest.raises(ValidationError, match="in order"):
        Manuscript.model_validate({**payload, "spreads": [spreads[1], spreads[0], *spreads[2:]]})
    with pytest.raises(ValidationError):
        Manuscript.model_validate(_ms(["a"] * 11))
