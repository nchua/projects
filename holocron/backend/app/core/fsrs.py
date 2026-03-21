"""
FSRS (Free Spaced Repetition Scheduler) implementation.

Based on the FSRS-4.5 algorithm. Three-component memory model:
  - Stability (S): days until retrievability drops to 90%
  - Difficulty (D): how hard the card is [0, 1]
  - Retrievability (R): probability of recall right now [0, 1]

Reference: https://github.com/open-spaced-repetition/py-fsrs
"""

import math
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from app.models.review import Rating


# Default FSRS-4.5 parameters (optimized on large review datasets)
FSRS_PARAMS = {
    # Initial stability values per first rating [forgot, struggled, got_it, easy]
    "w0": 0.4,    # forgot → very short
    "w1": 0.6,    # struggled
    "w2": 2.4,    # got_it
    "w3": 5.8,    # easy
    # Difficulty
    "w4": 4.93,   # initial difficulty mean
    "w5": 0.94,   # initial difficulty modifier
    "w6": 0.86,   # difficulty reversion toward mean
    "w7": 0.01,   # difficulty penalty for forgot
    # Stability after success
    "w8": 1.49,   # stability growth base
    "w9": 0.14,   # difficulty effect on growth
    "w10": 0.94,  # stability effect on growth
    "w11": 2.18,  # retrievability effect on growth
    # Stability after failure (lapse)
    "w12": 0.05,  # lapse multiplier
    "w13": 0.34,  # difficulty effect on lapse
    "w14": 1.26,  # stability effect on lapse
    "w15": 0.29,  # retrievability effect on lapse
    "w16": 0.2,   # minimum stability floor
}

# Map ratings to numeric grades (FSRS convention: 1=forgot, 2=struggled, 3=got_it, 4=easy)
RATING_TO_GRADE = {
    Rating.FORGOT: 1,
    Rating.STRUGGLED: 2,
    Rating.GOT_IT: 3,
    Rating.EASY: 4,
}

# AI-generated cards start with shorter intervals (no generation effect)
AI_CARD_STABILITY_FACTOR = 0.82  # 18% shorter


@dataclass
class ScheduleResult:
    """Result of scheduling a review."""

    difficulty: float
    stability: float
    retrievability: float
    next_review_at: datetime
    interval_days: float


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def calculate_retrievability(
    stability: float,
    elapsed_days: float,
) -> float:
    """Calculate current recall probability using the forgetting curve.

    R(t) = (1 + t / (9 * S))^(-1)

    Where t = elapsed days, S = stability.
    """
    if stability <= 0:
        return 0.0
    return (1 + elapsed_days / (9 * stability)) ** (-1)


def initial_difficulty(grade: int) -> float:
    """Calculate difficulty for a brand-new card based on first rating.

    D0(G) = w4 - (G - 3) * w5
    Clamped to [0.1, 0.9]
    """
    w = FSRS_PARAMS
    d = w["w4"] - (grade - 3) * w["w5"]
    return _clamp(d / 10, 0.1, 0.9)  # normalize to [0, 1]


def initial_stability(grade: int) -> float:
    """Get initial stability for a brand-new card.

    S0(G) = w[G-1]
    """
    key = f"w{grade - 1}"
    return FSRS_PARAMS[key]


def next_difficulty(d: float, grade: int) -> float:
    """Update difficulty after a review.

    D'(D, G) = w6 * D0(G) + (1 - w6) * (D - w7 * (G - 3))
    Mean-reversion: difficulty reverts toward the initial value.
    """
    w = FSRS_PARAMS
    d0 = initial_difficulty(grade)
    new_d = w["w6"] * d0 + (1 - w["w6"]) * (d - w["w7"] * (grade - 3))
    return _clamp(new_d, 0.1, 0.9)


def next_stability_success(s: float, d: float, r: float, grade: int) -> float:
    """Calculate new stability after a successful recall (grade >= 2).

    S'_success = S * (e^(w8) * (11 - D) * S^(-w10) * (e^(w11 * (1 - R)) - 1) * hard_factor + 1)

    Where hard_factor = w9 if grade == 2, else 1.
    """
    w = FSRS_PARAMS
    hard_factor = w["w9"] if grade == 2 else 1.0
    growth = (
        math.exp(w["w8"])
        * (11 - d * 10)  # un-normalize difficulty to ~[1, 9]
        * (s ** (-w["w10"]))
        * (math.exp(w["w11"] * (1 - r)) - 1)
        * hard_factor
        + 1
    )
    return max(0.1, s * growth)


def next_stability_fail(s: float, d: float, r: float) -> float:
    """Calculate new stability after a lapse (forgot).

    S'_fail = w12 * D^(-w13) * ((S + 1)^w14 - 1) * e^(w15 * (1 - R))
    """
    w = FSRS_PARAMS
    new_s = (
        w["w12"]
        * ((d * 10) ** (-w["w13"]))  # un-normalize
        * ((s + 1) ** w["w14"] - 1)
        * math.exp(w["w15"] * (1 - r))
    )
    return max(w["w16"], min(new_s, s))  # floor at w16, never exceed previous S


def optimal_interval(stability: float, target_retention: float = 0.9) -> float:
    """Calculate the optimal review interval in days.

    From the forgetting curve R(t) = (1 + t/(9S))^(-1), solving for t:
    t = 9 * S * (R^(-1) - 1)
    At target_retention=0.9: t ≈ S (roughly stability in days).
    """
    if stability <= 0:
        return 0.0
    interval = 9 * stability * (target_retention ** (-1) - 1)
    return max(0.01, interval)  # at least ~15 minutes


def schedule_review(
    rating: Rating,
    current_difficulty: float,
    current_stability: float,
    last_reviewed_at: datetime | None,
    review_count: int,
    ai_generated: bool = False,
    target_retention: float = 0.9,
    now: datetime | None = None,
) -> ScheduleResult:
    """Schedule the next review based on the user's rating.

    This is the main entry point for the FSRS engine.

    Args:
        rating: User's self-assessment (forgot/struggled/got_it/easy)
        current_difficulty: Card's current difficulty [0.1, 0.9]
        current_stability: Card's current stability (days)
        last_reviewed_at: When the card was last reviewed (None for new cards)
        review_count: How many times the card has been reviewed
        ai_generated: Whether the card was AI-generated (shorter initial intervals)
        target_retention: Desired recall probability (default 0.9)
        now: Current time (defaults to utcnow)

    Returns:
        ScheduleResult with updated parameters and next review date.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    grade = RATING_TO_GRADE[rating]

    # First review — use initial parameters
    if review_count == 0 or current_stability <= 0:
        difficulty = initial_difficulty(grade)
        stability = initial_stability(grade)

        # AI-generated cards get shorter initial stability
        if ai_generated:
            stability *= AI_CARD_STABILITY_FACTOR

        retrievability = 1.0
    else:
        # Calculate elapsed time and current retrievability
        if last_reviewed_at is not None:
            # Normalize timezone awareness for comparison
            reviewed = last_reviewed_at
            if reviewed.tzinfo is None:
                reviewed = reviewed.replace(tzinfo=timezone.utc)
            elapsed = (now - reviewed).total_seconds() / 86400
        else:
            elapsed = 0.0
        retrievability = calculate_retrievability(current_stability, elapsed)

        # Update difficulty
        difficulty = next_difficulty(current_difficulty, grade)

        # Update stability based on outcome
        if grade == 1:  # forgot
            stability = next_stability_fail(
                current_stability, difficulty, retrievability
            )
        else:
            stability = next_stability_success(
                current_stability, difficulty, retrievability, grade
            )

    # Calculate next interval
    interval_days = optimal_interval(stability, target_retention)

    # Clamp interval: at least 1 minute, at most 365 days
    interval_days = _clamp(interval_days, 1 / 1440, 365)

    next_review = now + timedelta(days=interval_days)

    return ScheduleResult(
        difficulty=round(difficulty, 4),
        stability=round(stability, 4),
        retrievability=round(retrievability, 4),
        next_review_at=next_review,
        interval_days=round(interval_days, 2),
    )
