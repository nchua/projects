"""Body recomposition and weight trend analysis."""

from .weight_trends import (
    WeightTrendAnalysis,
    analyze_weight_trends,
    calculate_rolling_average,
    detect_plateau,
    entries_to_dataframe,
    get_weight_history_summary,
)
from .inference import (
    RecompSignal,
    detect_recomp_signal,
    generate_recovery_alerts,
)

__all__ = [
    "WeightTrendAnalysis",
    "analyze_weight_trends",
    "calculate_rolling_average",
    "detect_plateau",
    "entries_to_dataframe",
    "get_weight_history_summary",
    "RecompSignal",
    "detect_recomp_signal",
    "generate_recovery_alerts",
]
