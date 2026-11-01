"""Word-length limits that used to be model validators (SPEC §4.3, §4.5).

They live here so an over-long artifact can still be loaded and flagged.
"""

from __future__ import annotations

from bookgen.models import CheckResult
from bookgen.textutil import count_words

RECAP_MAX_WORDS = 60
"""§4.5: the recap spread is at most 60 words."""

LEDGER_SUMMARY_MAX_WORDS = 120
"""§4.3: ``last_summary`` is at most 120 words; it feeds the recap."""


def max_words(code: str, text: str, limit: int, what: str) -> CheckResult:
    """Pass if ``text`` has at most ``limit`` words; ``what`` names it in the detail."""
    n = count_words(text)
    verdict = "within" if n <= limit else "over"
    detail = f"{what}: {n} words, {verdict} the {limit}-word limit"
    return CheckResult(code=code, passed=n <= limit, detail=detail, value=n)
