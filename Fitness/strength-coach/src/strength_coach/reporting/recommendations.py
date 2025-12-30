"""Training and nutrition recommendations generation."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .weekly_review import WeeklyReviewData


@dataclass
class Recommendation:
    """A single recommendation."""

    category: str  # "training", "recovery", "nutrition", "general"
    priority: str  # "high", "medium", "low"
    title: str
    details: str
    caveat: Optional[str] = None


def generate_training_recommendations(review: WeeklyReviewData) -> list[Recommendation]:
    """Generate training-focused recommendations based on weekly review."""
    recommendations: list[Recommendation] = []

    # Check for stalled lifts
    for lift, progress in review.lift_progress.items():
        if progress["trend"] == "down":
            recommendations.append(
                Recommendation(
                    category="training",
                    priority="high",
                    title=f"{lift.replace('_', ' ').title()} declining",
                    details=(
                        f"e1RM down {abs(progress['change_pct']):.1f}% over 4 weeks. "
                        "Consider: adjusting volume, adding variation, or taking a deload."
                    ),
                )
            )
        elif progress["trend"] == "stable" and progress["change_pct"] < 1:
            recommendations.append(
                Recommendation(
                    category="training",
                    priority="medium",
                    title=f"{lift.replace('_', ' ').title()} plateau",
                    details=(
                        "No significant progress in 4 weeks. Consider: "
                        "adding a variation (pause, tempo, deficit), "
                        "adjusting rep ranges, or increasing frequency."
                    ),
                )
            )

    # Volume recommendations
    total_sets = review.total_sets
    if review.session_count > 0:
        sets_per_session = total_sets / review.session_count

        if sets_per_session > 25:
            recommendations.append(
                Recommendation(
                    category="training",
                    priority="medium",
                    title="High volume per session",
                    details=(
                        f"Averaging {sets_per_session:.0f} sets/session. "
                        "Consider splitting into more frequent, shorter sessions "
                        "if recovery becomes an issue."
                    ),
                )
            )

    # Intensity distribution recommendations
    intensity = review.intensity
    heavy_pct = intensity.get("heavy", {}).get("pct", 0)
    hypertrophy_pct = intensity.get("hypertrophy", {}).get("pct", 0)

    if heavy_pct < 15:
        recommendations.append(
            Recommendation(
                category="training",
                priority="low",
                title="Consider adding heavy work",
                details=(
                    f"Only {heavy_pct:.0f}% of sets in 1-3 rep range. "
                    "For strength development, include some heavy singles, doubles, or triples."
                ),
            )
        )

    if hypertrophy_pct < 30:
        recommendations.append(
            Recommendation(
                category="training",
                priority="low",
                title="Consider more moderate rep work",
                details=(
                    f"Only {hypertrophy_pct:.0f}% of sets in 7-12 rep range. "
                    "This range is efficient for hypertrophy and may aid strength long-term."
                ),
            )
        )

    # Muscle group balance (simplified)
    muscle_vol = review.muscle_volume
    if muscle_vol:
        quads = muscle_vol.get("quads", {}).get("sets", 0)
        hamstrings = muscle_vol.get("hamstrings", {}).get("sets", 0)

        if quads > 0 and hamstrings < quads * 0.5:
            recommendations.append(
                Recommendation(
                    category="training",
                    priority="medium",
                    title="Consider more hamstring work",
                    details=(
                        f"Quad sets ({quads}) significantly exceed hamstring sets ({hamstrings}). "
                        "Consider adding RDLs, leg curls, or good mornings for balance."
                    ),
                )
            )

    return recommendations


def generate_recovery_recommendations(review: WeeklyReviewData) -> list[Recommendation]:
    """Generate recovery-focused recommendations."""
    recommendations: list[Recommendation] = []

    # High RPE warning
    if review.avg_session_rpe and review.avg_session_rpe > 8.5:
        recommendations.append(
            Recommendation(
                category="recovery",
                priority="high",
                title="High average RPE",
                details=(
                    f"Average session RPE is {review.avg_session_rpe:.1f}. "
                    "Consider scheduling a deload week if this persists."
                ),
            )
        )

    # Frequency check
    if review.session_count >= 5:
        recommendations.append(
            Recommendation(
                category="recovery",
                priority="medium",
                title="High training frequency",
                details=(
                    f"{review.session_count} sessions this week. "
                    "Ensure adequate sleep (7-9 hours) and nutrition to support recovery."
                ),
            )
        )

    # Weight loss + training load
    if review.weight_data:
        weekly_loss = review.weight_data.get("weekly_change", 0)
        if weekly_loss < -1.5 and review.session_count >= 4:
            recommendations.append(
                Recommendation(
                    category="recovery",
                    priority="high",
                    title="Aggressive cut with high training load",
                    details=(
                        f"Losing {abs(weekly_loss):.1f} lb/week with {review.session_count} sessions. "
                        "This may impair recovery. Consider reducing deficit or volume."
                    ),
                    caveat="Individual tolerance varies; monitor performance closely.",
                )
            )

    return recommendations


def generate_nutrition_recommendations(review: WeeklyReviewData) -> list[Recommendation]:
    """Generate nutrition-focused recommendations."""
    recommendations: list[Recommendation] = []

    # Weight trend based suggestions
    if review.weight_data:
        trend = review.weight_data.get("trend_4wk", "")
        weekly_change = review.weight_data.get("weekly_change", 0)

        # Recomp signal
        if review.recomp_signal and review.recomp_signal.get("is_likely"):
            recommendations.append(
                Recommendation(
                    category="nutrition",
                    priority="low",
                    title="Potential recomposition occurring",
                    details=(
                        "Weight stable with strength gains suggests body recomposition. "
                        "Continue current approach; ensure protein is adequate (0.7-1g/lb)."
                    ),
                    caveat="Actual body composition requires measurement (DEXA, etc.).",
                )
            )

        # Fast weight loss
        if weekly_change < -2:
            recommendations.append(
                Recommendation(
                    category="nutrition",
                    priority="high",
                    title="Rapid weight loss",
                    details=(
                        f"Losing {abs(weekly_change):.1f} lb/week is aggressive. "
                        "Risk of muscle loss increases. Consider slowing to 0.5-1 lb/week."
                    ),
                )
            )

        # Plateau
        if review.weight_data.get("alerts"):
            for alert in review.weight_data["alerts"]:
                if "plateau" in alert.lower():
                    recommendations.append(
                        Recommendation(
                            category="nutrition",
                            priority="medium",
                            title="Weight plateau detected",
                            details=(
                                "If cutting: consider a diet break (1-2 weeks at maintenance). "
                                "If bulking: may have reached new maintenance level."
                            ),
                        )
                    )
                    break

    return recommendations


def generate_all_recommendations(review: WeeklyReviewData) -> list[Recommendation]:
    """Generate all recommendations for a weekly review."""
    all_recs: list[Recommendation] = []

    all_recs.extend(generate_training_recommendations(review))
    all_recs.extend(generate_recovery_recommendations(review))
    all_recs.extend(generate_nutrition_recommendations(review))

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    all_recs.sort(key=lambda r: priority_order.get(r.priority, 3))

    return all_recs
