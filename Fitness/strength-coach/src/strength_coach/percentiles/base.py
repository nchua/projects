"""Abstract interface for percentile calculation."""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class PercentileResult(BaseModel):
    """Result from percentile calculation."""

    lift: str
    e1rm_lb: Decimal
    bodyweight_lb: Decimal
    sex: str
    age: int
    percentile: float
    classification: str  # "Beginner", "Novice", "Intermediate", "Advanced", "Elite"
    wilks_coefficient: Optional[float] = None
    bodyweight_multiple: float
    source: str

    @property
    def bw_ratio_display(self) -> str:
        """Display format for bodyweight multiple."""
        return f"{self.bodyweight_multiple:.2f}x BW"


class PercentileProvider(ABC):
    """
    Abstract interface for strength percentile calculation.

    Implementations can use different data sources (hardcoded, API, etc.)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for display."""
        ...

    @property
    @abstractmethod
    def supported_lifts(self) -> list[str]:
        """List of lift IDs this provider supports."""
        ...

    @abstractmethod
    def get_percentile(
        self,
        lift: str,
        e1rm_lb: Decimal,
        bodyweight_lb: Decimal,
        sex: str,
        age: int,
    ) -> PercentileResult:
        """
        Calculate strength percentile for a lift.

        Args:
            lift: Canonical lift ID (squat, bench_press, deadlift, overhead_press)
            e1rm_lb: Estimated 1RM in pounds
            bodyweight_lb: User's bodyweight in pounds
            sex: "male" or "female"
            age: User's age in years

        Returns:
            PercentileResult with percentile and classification
        """
        ...

    def get_all_percentiles(
        self,
        lifts: dict[str, Decimal],
        bodyweight_lb: Decimal,
        sex: str,
        age: int,
    ) -> dict[str, PercentileResult]:
        """
        Get percentiles for multiple lifts at once.

        Args:
            lifts: Dict mapping lift ID to e1RM
            bodyweight_lb: User's bodyweight
            sex: User's sex
            age: User's age

        Returns:
            Dict mapping lift ID to PercentileResult
        """
        results = {}
        for lift, e1rm in lifts.items():
            if lift in self.supported_lifts:
                results[lift] = self.get_percentile(lift, e1rm, bodyweight_lb, sex, age)
        return results


def classify_from_percentile(percentile: float) -> str:
    """Convert percentile to classification."""
    if percentile >= 95:
        return "Elite"
    elif percentile >= 80:
        return "Advanced"
    elif percentile >= 50:
        return "Intermediate"
    elif percentile >= 20:
        return "Novice"
    else:
        return "Beginner"
