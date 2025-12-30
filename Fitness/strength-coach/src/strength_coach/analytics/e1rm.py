"""Estimated 1 rep max (e1RM) calculations."""

from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional

from ..models import SetRecord


class E1RMFormula(str, Enum):
    """Available 1RM estimation formulas."""

    EPLEY = "epley"
    BRZYCKI = "brzycki"
    LOMBARDI = "lombardi"
    MAYHEW = "mayhew"
    OCONNER = "oconner"
    WATHAN = "wathan"


# Maximum reliable rep count for e1RM estimation
MAX_RELIABLE_REPS = 12


def estimate_e1rm(
    weight: Decimal,
    reps: int,
    formula: E1RMFormula = E1RMFormula.EPLEY,
) -> Decimal:
    """
    Estimate 1RM from weight and reps using specified formula.

    Args:
        weight: Weight lifted
        reps: Number of reps completed
        formula: Which formula to use (default: Epley)

    Returns:
        Estimated 1RM, or Decimal("0") if reps > MAX_RELIABLE_REPS

    Note:
        For reps == 1, returns the weight itself.
        For reps > 12, returns 0 (unreliable estimate).
    """
    if reps <= 0:
        return Decimal("0")

    if reps == 1:
        return weight

    if reps > MAX_RELIABLE_REPS:
        return Decimal("0")

    weight_float = float(weight)
    result: float

    match formula:
        case E1RMFormula.EPLEY:
            # e1RM = weight * (1 + reps/30)
            result = weight_float * (1 + reps / 30)

        case E1RMFormula.BRZYCKI:
            # e1RM = weight * 36 / (37 - reps)
            result = weight_float * 36 / (37 - reps)

        case E1RMFormula.LOMBARDI:
            # e1RM = weight * reps^0.1
            result = weight_float * (reps**0.1)

        case E1RMFormula.MAYHEW:
            # e1RM = 100 * weight / (52.2 + 41.9 * e^(-0.055 * reps))
            import math

            result = 100 * weight_float / (52.2 + 41.9 * math.exp(-0.055 * reps))

        case E1RMFormula.OCONNER:
            # e1RM = weight * (1 + 0.025 * reps)
            result = weight_float * (1 + 0.025 * reps)

        case E1RMFormula.WATHAN:
            # e1RM = 100 * weight / (48.8 + 53.8 * e^(-0.075 * reps))
            import math

            result = 100 * weight_float / (48.8 + 53.8 * math.exp(-0.075 * reps))

        case _:
            # Default to Epley
            result = weight_float * (1 + reps / 30)

    return Decimal(str(result)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def estimate_e1rm_multi(
    weight: Decimal,
    reps: int,
    formulas: Optional[list[E1RMFormula]] = None,
) -> dict[E1RMFormula, Decimal]:
    """
    Estimate 1RM using multiple formulas.

    Args:
        weight: Weight lifted
        reps: Number of reps completed
        formulas: List of formulas to use (default: Epley and Brzycki)

    Returns:
        Dictionary mapping formula to estimated 1RM
    """
    if formulas is None:
        formulas = [E1RMFormula.EPLEY, E1RMFormula.BRZYCKI]

    return {formula: estimate_e1rm(weight, reps, formula) for formula in formulas}


def calculate_set_e1rm(
    set_record: SetRecord,
    formulas: Optional[list[E1RMFormula]] = None,
) -> dict[str, Decimal]:
    """
    Calculate e1RM for a single set.

    Args:
        set_record: The set to analyze
        formulas: Formulas to use (default: Epley, Brzycki)

    Returns:
        Dictionary with formula names and "default" (Epley)
    """
    if formulas is None:
        formulas = [E1RMFormula.EPLEY, E1RMFormula.BRZYCKI]

    results: dict[str, Decimal] = {}

    for formula in formulas:
        e1rm = estimate_e1rm(set_record.weight_lb, set_record.reps, formula)
        results[formula.value] = e1rm

    # Default is always Epley
    results["default"] = estimate_e1rm(
        set_record.weight_lb, set_record.reps, E1RMFormula.EPLEY
    )

    return results


def is_reliable_estimate(reps: int) -> bool:
    """Check if e1RM estimate is considered reliable for given rep count."""
    return 1 <= reps <= MAX_RELIABLE_REPS


def get_percentage_of_1rm(reps: int) -> float:
    """
    Get approximate percentage of 1RM for a given rep count.

    Based on commonly used rep-percentage tables.
    """
    percentages = {
        1: 100.0,
        2: 95.0,
        3: 93.0,
        4: 90.0,
        5: 87.0,
        6: 85.0,
        7: 83.0,
        8: 80.0,
        9: 77.0,
        10: 75.0,
        11: 73.0,
        12: 70.0,
    }
    return percentages.get(reps, 65.0 if reps > 12 else 0.0)


def estimate_reps_at_weight(
    e1rm: Decimal,
    target_weight: Decimal,
) -> int:
    """
    Estimate how many reps can be performed at a given weight.

    Uses Epley formula inverted.
    """
    if target_weight >= e1rm:
        return 1

    if target_weight <= Decimal("0"):
        return 0

    # From Epley: e1rm = weight * (1 + reps/30)
    # Solving for reps: reps = 30 * (e1rm/weight - 1)
    ratio = float(e1rm / target_weight)
    reps = 30 * (ratio - 1)

    return max(1, min(int(reps), 30))  # Cap at 30 reps
