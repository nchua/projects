"""Analytics modules for strength coach."""

from .e1rm import (
    E1RMFormula,
    estimate_e1rm,
    estimate_e1rm_multi,
    calculate_set_e1rm,
    is_reliable_estimate,
    get_percentage_of_1rm,
    estimate_reps_at_weight,
)
from .trends import (
    exercise_sets_to_dataframe,
    get_weekly_best_e1rm,
    get_rolling_avg_e1rm,
    get_exercise_trend,
    compare_exercises,
)
from .prs import (
    PRRecord,
    detect_set_prs,
    detect_exercise_prs,
    detect_session_prs,
    build_pr_history,
    format_pr_for_display,
)
from .volume import (
    VolumeMetrics,
    MuscleVolumeMetrics,
    calculate_exercise_volume,
    calculate_session_volume,
    calculate_muscle_group_volume,
    calculate_weekly_volume,
    calculate_weekly_muscle_volume,
    get_volume_trend,
    compare_volume_to_previous_week,
)
from .intensity import (
    IntensityDistribution,
    RepRangeBucket,
    calculate_exercise_intensity,
    calculate_session_intensity,
    calculate_weekly_intensity,
    analyze_intensity_by_exercise,
    get_average_reps_per_set,
    get_intensity_recommendation,
)

__all__ = [
    # e1RM
    "E1RMFormula",
    "estimate_e1rm",
    "estimate_e1rm_multi",
    "calculate_set_e1rm",
    "is_reliable_estimate",
    "get_percentage_of_1rm",
    "estimate_reps_at_weight",
    # Trends
    "exercise_sets_to_dataframe",
    "get_weekly_best_e1rm",
    "get_rolling_avg_e1rm",
    "get_exercise_trend",
    "compare_exercises",
    # PRs
    "PRRecord",
    "detect_set_prs",
    "detect_exercise_prs",
    "detect_session_prs",
    "build_pr_history",
    "format_pr_for_display",
    # Volume
    "VolumeMetrics",
    "MuscleVolumeMetrics",
    "calculate_exercise_volume",
    "calculate_session_volume",
    "calculate_muscle_group_volume",
    "calculate_weekly_volume",
    "calculate_weekly_muscle_volume",
    "get_volume_trend",
    "compare_volume_to_previous_week",
    # Intensity
    "IntensityDistribution",
    "RepRangeBucket",
    "calculate_exercise_intensity",
    "calculate_session_intensity",
    "calculate_weekly_intensity",
    "analyze_intensity_by_exercise",
    "get_average_reps_per_set",
    "get_intensity_recommendation",
]
