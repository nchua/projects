"""Word and sentence tokenising shared by models and the mechanical checks (SPEC §6.3).

Deliberately simple and deterministic: a word is a run of letters/digits that may
contain an apostrophe or hyphen ("don't", "half-asleep" are one word); a sentence
ends at ``.``, ``!``, ``?`` or an ellipsis followed by a capitalised word or the end
of the text, so ``"Wait!" said Maya.`` stays one sentence.
"""

from __future__ import annotations

import re

WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")
"""One word, apostrophes and inner hyphens included."""

_SENTENCE_END_RE = re.compile(r"((?:[.!?]+|…)[\"'”’)\]]*)\s+(?=[\"'“‘(\[]*[A-Z0-9])")
"""A sentence boundary: terminal punctuation, optional closing quotes, space, capital."""


def words(text: str) -> list[str]:
    """Return the words of ``text`` in order."""
    return WORD_RE.findall(text)


def count_words(text: str) -> int:
    """Return the number of words in ``text``."""
    return len(words(text))


def sentences(text: str) -> list[str]:
    """Split ``text`` into sentences, dropping empty fragments."""
    text = text.strip()
    parts, start = [], 0
    for m in _SENTENCE_END_RE.finditer(text):
        parts.append(text[start : m.end(1)])
        start = m.end()
    parts.append(text[start:])
    return [p.strip() for p in parts if words(p)]
