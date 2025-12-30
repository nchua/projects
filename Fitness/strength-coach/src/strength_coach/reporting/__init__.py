"""Reporting and output generation."""

from .weekly_review import (
    WeeklyHighlight,
    WeeklyReviewData,
    generate_weekly_review,
)
from .recommendations import (
    Recommendation,
    generate_training_recommendations,
    generate_recovery_recommendations,
    generate_nutrition_recommendations,
    generate_all_recommendations,
)
from .markdown import (
    generate_weekly_report_markdown,
    generate_lift_progress_markdown,
    format_lift_name,
)

__all__ = [
    "WeeklyHighlight",
    "WeeklyReviewData",
    "generate_weekly_review",
    "Recommendation",
    "generate_training_recommendations",
    "generate_recovery_recommendations",
    "generate_nutrition_recommendations",
    "generate_all_recommendations",
    "generate_weekly_report_markdown",
    "generate_lift_progress_markdown",
    "format_lift_name",
]
