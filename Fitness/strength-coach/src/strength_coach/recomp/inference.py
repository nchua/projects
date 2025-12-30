"""Recomposition inference and signals."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .weight_trends import WeightTrendAnalysis


@dataclass
class RecompSignal:
    """Inferred recomposition signal."""

    is_recomp_likely: bool
    confidence: str  # "low", "medium", "high"
    explanation: str
    recommendations: list[str]
    caveats: list[str]


def detect_recomp_signal(
    weight_analysis: WeightTrendAnalysis,
    strength_trend: dict,
    volume_trend: Optional[dict] = None,
) -> RecompSignal:
    """
    Infer potential body recomposition from weight and strength trends.

    Body recomposition (losing fat while gaining muscle) is suggested when:
    - Weight is relatively stable
    - Strength is increasing
    - Volume is maintained or increasing

    Note: This is inference only; actual body composition requires DEXA or similar.

    Args:
        weight_analysis: Results from weight trend analysis
        strength_trend: Dict with e1rm_change_pct and trend_direction
        volume_trend: Optional dict with volume change data

    Returns:
        RecompSignal with assessment and recommendations
    """
    caveats = [
        "Body composition cannot be accurately measured from weight and strength alone.",
        "For definitive results, consider DEXA scan or similar body composition analysis.",
        "Strength increases can occur without muscle gain (neural adaptation).",
    ]

    # Insufficient data
    if weight_analysis.data_quality == "insufficient":
        return RecompSignal(
            is_recomp_likely=False,
            confidence="low",
            explanation="Insufficient weight data to assess recomposition.",
            recommendations=["Log weight consistently for 2-4 weeks to enable analysis."],
            caveats=caveats,
        )

    if strength_trend.get("trend_direction") == "insufficient_data":
        return RecompSignal(
            is_recomp_likely=False,
            confidence="low",
            explanation="Insufficient training data to assess recomposition.",
            recommendations=["Continue training consistently for trend analysis."],
            caveats=caveats,
        )

    # Extract metrics
    weight_stable = weight_analysis.trend_4wk == "stable"
    weight_losing = weight_analysis.trend_4wk == "losing"
    weight_gaining = weight_analysis.trend_4wk == "gaining"

    strength_up = strength_trend.get("trend_direction") == "up"
    strength_change = strength_trend.get("e1rm_change_pct", 0)

    # Volume maintained or up
    volume_maintained = True
    if volume_trend:
        vol_change = volume_trend.get("change", {}).get("sets_pct", 0)
        volume_maintained = vol_change >= -10  # Allow 10% drop

    # Case 1: Weight stable + strength up = likely recomp
    if weight_stable and strength_up and strength_change > 2:
        confidence = "medium" if strength_change > 5 else "low"
        return RecompSignal(
            is_recomp_likely=True,
            confidence=confidence,
            explanation=(
                f"Weight stable ({weight_analysis.rolling_7day_avg:.1f} lb avg) while "
                f"strength increased {strength_change:.1f}%. This pattern is consistent "
                "with body recomposition (fat loss + muscle gain)."
            ),
            recommendations=[
                "Continue current approach - it appears to be working.",
                "Ensure adequate protein intake (0.7-1g per lb bodyweight).",
                "Consider periodic progress photos for visual confirmation.",
            ],
            caveats=caveats,
        )

    # Case 2: Weight slightly losing + strength up = likely recomp
    if weight_losing and strength_up:
        weekly_loss = abs(float(weight_analysis.weekly_change_lb))
        if weekly_loss <= 1.0:  # Slow cut
            return RecompSignal(
                is_recomp_likely=True,
                confidence="medium",
                explanation=(
                    f"Weight decreasing slowly ({weekly_loss:.1f} lb/week) while "
                    f"strength is up {strength_change:.1f}%. This suggests fat loss "
                    "while preserving or building muscle."
                ),
                recommendations=[
                    "Excellent progress - slow cuts preserve muscle better.",
                    "Maintain protein intake to support muscle retention.",
                    "Monitor strength; if it drops, consider eating slightly more.",
                ],
                caveats=caveats,
            )

    # Case 3: Weight gaining but not too fast + strength up
    if weight_gaining and strength_up:
        weekly_gain = float(weight_analysis.weekly_change_lb)
        if weekly_gain <= 0.5:  # Lean bulk
            return RecompSignal(
                is_recomp_likely=False,  # This is more of a lean bulk
                confidence="low",
                explanation=(
                    f"Slow weight gain ({weekly_gain:.1f} lb/week) with strength gains. "
                    "This is more characteristic of a lean bulk than recomposition."
                ),
                recommendations=[
                    "Good rate of gain for minimizing fat accumulation.",
                    "Continue tracking to ensure gains remain controlled.",
                ],
                caveats=caveats,
            )

    # Case 4: Strength stagnant or declining
    if not strength_up:
        if weight_losing:
            return RecompSignal(
                is_recomp_likely=False,
                confidence="medium",
                explanation=(
                    "Weight decreasing but strength not improving. This suggests "
                    "primarily fat loss without significant muscle gain."
                ),
                recommendations=[
                    "If cutting, this is normal - focus on strength maintenance.",
                    "Ensure protein intake is adequate.",
                    "Consider reducing caloric deficit if strength drops significantly.",
                ],
                caveats=caveats,
            )
        else:
            return RecompSignal(
                is_recomp_likely=False,
                confidence="low",
                explanation="Strength not increasing. Recomposition requires progressive overload.",
                recommendations=[
                    "Focus on progressive overload in training.",
                    "Review program structure and recovery.",
                    "Ensure adequate sleep and nutrition.",
                ],
                caveats=caveats,
            )

    # Default case
    return RecompSignal(
        is_recomp_likely=False,
        confidence="low",
        explanation="Trends are unclear. Continue tracking for more definitive analysis.",
        recommendations=[
            "Maintain consistent tracking for 4+ weeks.",
            "Focus on progressive overload in training.",
            "Ensure adequate protein and sleep.",
        ],
        caveats=caveats,
    )


def generate_recovery_alerts(
    weight_analysis: WeightTrendAnalysis,
    avg_session_rpe: Optional[float],
    training_frequency: int,
) -> list[str]:
    """
    Generate alerts related to recovery and potential under-recovery.

    Args:
        weight_analysis: Weight trend data
        avg_session_rpe: Average RPE across recent sessions
        training_frequency: Sessions per week

    Returns:
        List of alert messages
    """
    alerts: list[str] = []

    # Rapid weight loss + high training load
    if weight_analysis.trend_4wk == "losing":
        weekly_loss = abs(float(weight_analysis.weekly_change_lb))
        if weekly_loss > 1.5 and training_frequency >= 4:
            alerts.append(
                f"High training frequency ({training_frequency}x/week) with aggressive "
                f"weight loss ({weekly_loss:.1f} lb/week) may impair recovery."
            )

    # High RPE + weight loss
    if avg_session_rpe and avg_session_rpe > 8.5:
        alerts.append(
            f"Average session RPE is high ({avg_session_rpe:.1f}). "
            "Consider a deload if performance is declining."
        )

    # Extended plateau may indicate adaptation stall
    if weight_analysis.days_at_plateau > 28:
        alerts.append(
            f"Weight plateau for {weight_analysis.days_at_plateau} days. "
            "If cutting, consider a diet break or refeed."
        )

    return alerts
