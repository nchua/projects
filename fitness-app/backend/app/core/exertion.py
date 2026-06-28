"""
Exertion score for wearable cardio sessions.

WHOOP supplies a proprietary "strain" value, but Apple-Watch sessions never
carry one. This module derives a comparable 0-21 ``exertion_score`` purely from
the time-in-HR-zone breakdown (``hr_zone_seconds``) that the HealthKit import
already captures, so a run/tennis match logged from the Watch gets a meaningful
exertion number in the History row.

The score is intentionally a transparent heuristic (intensity x duration), NOT a
reproduction of WHOOP's algorithm: it weights seconds spent in higher zones more
heavily and scales the total cardiovascular load onto a 0-21 range.
"""
from typing import Dict, Optional

# Per-zone intensity weight. z5 (near-max) counts 5x as much per second as z1.
ZONE_WEIGHTS: Dict[str, float] = {
    "z1": 1.0,
    "z2": 2.0,
    "z3": 3.0,
    "z4": 4.0,
    "z5": 5.0,
}

# Weighted-seconds that map to the top of the 0-21 range. 18000 ≈ one hour held
# entirely in z5 (5 weight x 3600 s). An hour in z3 lands at ~12.6, an hour in
# z2 at ~8.4 — a reasonable strain-like curve that grows with both intensity and
# duration.
WEIGHTED_SECONDS_FOR_MAX = 18000.0

MAX_EXERTION = 21.0


def compute_exertion_score(hr_zone_seconds: Optional[Dict[str, int]]) -> Optional[float]:
    """Derive a 0-21 exertion score from a time-in-zone breakdown.

    Args:
        hr_zone_seconds: Mapping of zone name -> seconds, e.g.
            ``{"z1": 120, "z2": 540, "z3": 300}``. ``None``/empty yields ``None``.

    Returns:
        Exertion score rounded to one decimal in ``[0, 21]``, or ``None`` when no
        usable zone data is present (so callers can fall back to WHOOP strain).
    """
    if not hr_zone_seconds:
        return None

    total_seconds = 0.0
    weighted_seconds = 0.0
    for zone, seconds in hr_zone_seconds.items():
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            continue
        total_seconds += seconds
        weighted_seconds += ZONE_WEIGHTS.get(str(zone).lower(), 0.0) * seconds

    if total_seconds <= 0:
        return None

    score = round(min(MAX_EXERTION, MAX_EXERTION * weighted_seconds / WEIGHTED_SECONDS_FOR_MAX), 1)
    # A score that rounds to zero (only unrecognized zones, or a sub-rounding
    # blip) carries no signal — return None so clients hide it rather than
    # showing a meaningless "0.0 exertion".
    if score <= 0:
        return None
    return score
