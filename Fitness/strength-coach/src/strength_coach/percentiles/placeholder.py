"""Placeholder percentile provider with hardcoded data.

Based on approximate data from Symmetric Strength and Strength Level.
These values are approximations for demonstration purposes.
"""

from decimal import Decimal
from typing import ClassVar

from .base import PercentileProvider, PercentileResult, classify_from_percentile


# Approximate bodyweight multiplier thresholds for male lifters
# Format: {lift: [(bw_multiplier, percentile), ...]} sorted ascending
MALE_STANDARDS: dict[str, list[tuple[float, float]]] = {
    "squat": [
        (0.75, 10),
        (1.0, 20),
        (1.25, 35),
        (1.5, 50),
        (1.75, 65),
        (2.0, 80),
        (2.25, 90),
        (2.5, 95),
        (2.75, 98),
    ],
    "bench_press": [
        (0.5, 10),
        (0.75, 20),
        (1.0, 40),
        (1.25, 55),
        (1.5, 75),
        (1.75, 85),
        (2.0, 93),
        (2.25, 97),
    ],
    "deadlift": [
        (1.0, 10),
        (1.25, 20),
        (1.5, 35),
        (1.75, 50),
        (2.0, 65),
        (2.25, 75),
        (2.5, 85),
        (2.75, 92),
        (3.0, 96),
    ],
    "overhead_press": [
        (0.35, 10),
        (0.5, 25),
        (0.65, 45),
        (0.8, 60),
        (1.0, 80),
        (1.15, 90),
        (1.3, 95),
    ],
    "sumo_deadlift": [  # Same as conventional for simplicity
        (1.0, 10),
        (1.25, 20),
        (1.5, 35),
        (1.75, 50),
        (2.0, 65),
        (2.25, 75),
        (2.5, 85),
        (2.75, 92),
        (3.0, 96),
    ],
}

# Female standards (roughly 70-75% of male standards for comparable percentiles)
FEMALE_STANDARDS: dict[str, list[tuple[float, float]]] = {
    "squat": [
        (0.5, 10),
        (0.75, 25),
        (1.0, 45),
        (1.25, 65),
        (1.5, 80),
        (1.75, 90),
        (2.0, 96),
    ],
    "bench_press": [
        (0.35, 15),
        (0.5, 35),
        (0.65, 50),
        (0.85, 70),
        (1.0, 85),
        (1.15, 93),
        (1.3, 97),
    ],
    "deadlift": [
        (0.75, 10),
        (1.0, 25),
        (1.25, 45),
        (1.5, 65),
        (1.75, 80),
        (2.0, 90),
        (2.25, 95),
    ],
    "overhead_press": [
        (0.25, 15),
        (0.35, 30),
        (0.45, 50),
        (0.55, 70),
        (0.7, 85),
        (0.85, 93),
    ],
    "sumo_deadlift": [
        (0.75, 10),
        (1.0, 25),
        (1.25, 45),
        (1.5, 65),
        (1.75, 80),
        (2.0, 90),
        (2.25, 95),
    ],
}


def interpolate_percentile(bw_mult: float, standards: list[tuple[float, float]]) -> float:
    """
    Interpolate percentile from bodyweight multiplier.

    Linear interpolation between known points.
    """
    if not standards:
        return 50.0

    # Below minimum
    if bw_mult <= standards[0][0]:
        return standards[0][1] * (bw_mult / standards[0][0])

    # Above maximum
    if bw_mult >= standards[-1][0]:
        return min(99.0, standards[-1][1] + (bw_mult - standards[-1][0]) * 5)

    # Find surrounding points and interpolate
    for i in range(len(standards) - 1):
        low_mult, low_pct = standards[i]
        high_mult, high_pct = standards[i + 1]

        if low_mult <= bw_mult <= high_mult:
            # Linear interpolation
            ratio = (bw_mult - low_mult) / (high_mult - low_mult)
            return low_pct + ratio * (high_pct - low_pct)

    return 50.0  # Fallback


class PlaceholderPercentileProvider(PercentileProvider):
    """
    Hardcoded percentile provider for demonstration.

    Uses approximate data based on Symmetric Strength standards.
    Should be replaced with a real data source for production use.
    """

    SUPPORTED_LIFTS: ClassVar[list[str]] = [
        "squat",
        "bench_press",
        "deadlift",
        "overhead_press",
        "sumo_deadlift",
    ]

    @property
    def name(self) -> str:
        return "Placeholder (approximate)"

    @property
    def supported_lifts(self) -> list[str]:
        return self.SUPPORTED_LIFTS

    def get_percentile(
        self,
        lift: str,
        e1rm_lb: Decimal,
        bodyweight_lb: Decimal,
        sex: str,
        age: int,
    ) -> PercentileResult:
        """Calculate percentile using hardcoded standards."""
        if lift not in self.SUPPORTED_LIFTS:
            raise ValueError(f"Unsupported lift: {lift}. Supported: {self.SUPPORTED_LIFTS}")

        # Calculate bodyweight multiple
        bw_mult = float(e1rm_lb / bodyweight_lb) if bodyweight_lb > 0 else 0

        # Select standards based on sex
        standards = MALE_STANDARDS if sex == "male" else FEMALE_STANDARDS

        # Get standards for this lift
        lift_standards = standards.get(lift, [])

        # Interpolate percentile
        percentile = interpolate_percentile(bw_mult, lift_standards)

        # Apply age adjustment (slight penalty for older, slight boost for younger)
        # This is a rough approximation
        if age < 25:
            age_factor = 1.0 + (25 - age) * 0.005  # Up to 7.5% boost
        elif age > 35:
            age_factor = 1.0 - (age - 35) * 0.003  # Up to ~10% penalty at 70
        else:
            age_factor = 1.0

        adjusted_percentile = min(99.0, max(1.0, percentile * age_factor))

        return PercentileResult(
            lift=lift,
            e1rm_lb=e1rm_lb,
            bodyweight_lb=bodyweight_lb,
            sex=sex,
            age=age,
            percentile=round(adjusted_percentile, 1),
            classification=classify_from_percentile(adjusted_percentile),
            bodyweight_multiple=round(bw_mult, 2),
            source=self.name,
        )


# Default provider instance
default_provider = PlaceholderPercentileProvider()
