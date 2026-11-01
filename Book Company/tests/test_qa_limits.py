"""Word limits are QA checks that flag, not validators that refuse to load."""

from __future__ import annotations

from bookgen.qa.limits import RECAP_MAX_WORDS, max_words


def test_max_words_pass_and_fail() -> None:
    """At the limit passes; one over fails with the count in the detail."""
    ok = max_words("recap_length", "word " * RECAP_MAX_WORDS, RECAP_MAX_WORDS, "recap")
    assert ok.passed and ok.value == 60
    over = max_words("recap_length", "word " * 61, RECAP_MAX_WORDS, "recap")
    assert not over.passed and "61 words" in over.detail
