"""
Estimated 1RM (e1RM) calculation functions
"""
from app.models.user import E1RMFormula


def calculate_e1rm(weight: float, reps: int, formula: E1RMFormula = E1RMFormula.EPLEY) -> float:
    """
    Calculate estimated 1 rep max using various formulas

    Args:
        weight: Weight lifted
        reps: Number of reps completed
        formula: Formula to use for calculation

    Returns:
        Estimated 1RM

    Note:
        All formulas are less accurate above 10-12 reps
        Returns weight itself if reps = 1
    """
    if reps == 1:
        return weight

    if formula == E1RMFormula.EPLEY:
        # Epley Formula: weight * (1 + reps/30)
        return weight * (1 + reps / 30)

    elif formula == E1RMFormula.BRZYCKI:
        # Brzycki Formula: weight * (36 / (37 - reps))
        return weight * (36 / (37 - reps))

    elif formula == E1RMFormula.WATHAN:
        # Wathan Formula: (100 * weight) / (48.8 + 53.8 * e^(-0.075 * reps))
        import math
        return (100 * weight) / (48.8 + 53.8 * math.exp(-0.075 * reps))

    elif formula == E1RMFormula.LOMBARDI:
        # Lombardi Formula: weight * reps^0.1
        return weight * (reps ** 0.1)

    else:
        # Default to Epley
        return weight * (1 + reps / 30)


def calculate_e1rm_from_rpe(weight: float, reps: int, rpe: int, formula: E1RMFormula = E1RMFormula.EPLEY) -> float:
    """
    Calculate e1RM adjusted for RPE (Rate of Perceived Exertion)

    Args:
        weight: Weight lifted
        reps: Number of reps completed
        rpe: RPE value (1-10)
        formula: Formula to use for calculation

    Returns:
        Estimated 1RM adjusted for RPE

    Note:
        RPE 10 = max effort (0 RIR)
        RPE 9 = 1 rep in reserve
        RPE 8 = 2 reps in reserve
        etc.
    """
    # Convert RPE to RIR (Reps in Reserve)
    rir = 10 - rpe

    # Adjust reps to account for RIR
    adjusted_reps = reps + rir

    # Calculate e1RM with adjusted reps
    return calculate_e1rm(weight, adjusted_reps, formula)


def calculate_e1rm_from_rir(weight: float, reps: int, rir: int, formula: E1RMFormula = E1RMFormula.EPLEY) -> float:
    """
    Calculate e1RM adjusted for RIR (Reps in Reserve)

    Args:
        weight: Weight lifted
        reps: Number of reps completed
        rir: Reps in reserve (0-5)
        formula: Formula to use for calculation

    Returns:
        Estimated 1RM adjusted for RIR
    """
    # Adjust reps to account for RIR
    adjusted_reps = reps + rir

    # Calculate e1RM with adjusted reps
    return calculate_e1rm(weight, adjusted_reps, formula)
