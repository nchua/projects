"""Mechanical checks: code, not models (SPEC §6.3, §6.4).

Every check returns ``CheckResult`` objects; the stage hands them to the runner,
which records all of them and turns failures into flags. Nothing here raises
on bad content, so an over-long recap is a flag the editor fixes, not a crash.
"""

from __future__ import annotations

from collections.abc import Sequence

from bookgen.models import CheckResult


def per_spread(code: str, failures: dict[int | str, str], ok: str = "") -> list[CheckResult]:
    """One failing result per slot in ``failures``, or a single passing result.

    Slots are story spreads (``int``, carried into the flag) or cover/recap/teaser.
    """
    if not failures:
        return [CheckResult(code=code, passed=True, detail=ok)]
    return [
        CheckResult(
            code=code, passed=False, detail=d, spread=slot if isinstance(slot, int) else None
        )
        for slot, d in failures.items()
    ]


def none_of(code: str, items: Sequence[object], label: str) -> CheckResult:
    """Pass when ``items`` is empty; otherwise fail and list them after ``label``."""
    return CheckResult(
        code=code, passed=not items, detail=f"{label}: {list(items)}" if items else ""
    )
