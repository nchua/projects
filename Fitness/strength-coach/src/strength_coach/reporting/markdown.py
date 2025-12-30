"""Markdown report generation."""

from datetime import date
from typing import Optional

from .weekly_review import WeeklyReviewData
from .recommendations import Recommendation, generate_all_recommendations
from ..analytics import format_pr_for_display


def format_lift_name(lift_id: str) -> str:
    """Convert lift ID to display name."""
    names = {
        "squat": "Squat",
        "bench_press": "Bench Press",
        "deadlift": "Deadlift",
        "overhead_press": "OHP",
        "sumo_deadlift": "Sumo Deadlift",
    }
    return names.get(lift_id, lift_id.replace("_", " ").title())


def trend_emoji(direction: str) -> str:
    """Get emoji for trend direction."""
    return {"up": "+", "down": "-", "stable": "=", "insufficient_data": "?"}.get(direction, "")


def generate_weekly_report_markdown(
    review: WeeklyReviewData,
    include_recommendations: bool = True,
) -> str:
    """
    Generate a full weekly report in Markdown format.

    Args:
        review: WeeklyReviewData from generate_weekly_review
        include_recommendations: Whether to include recommendations section

    Returns:
        Formatted Markdown string
    """
    lines: list[str] = []

    # Header
    lines.append("# Weekly Training Review")
    lines.append(
        f"**Week of {review.week_start.strftime('%b %d')} - "
        f"{review.week_end.strftime('%b %d, %Y')}**"
    )
    lines.append("")

    # Summary section
    lines.append("## Summary")
    lines.append(f"- **Sessions:** {review.session_count} ({', '.join(review.session_days)})")
    lines.append(
        f"- **Total Volume:** {review.total_volume_lb:,.0f} lb across {review.total_sets} working sets"
    )
    if review.avg_session_rpe:
        lines.append(f"- **Avg Session RPE:** {review.avg_session_rpe:.1f}")
    lines.append("")

    # Highlights
    if review.highlights:
        lines.append("## Highlights")
        for highlight in review.highlights[:5]:  # Top 5
            prefix = {"pr": "**PR:**", "volume": "", "consistency": "", "warning": "**Note:**"}.get(
                highlight.type, ""
            )
            lines.append(f"- {prefix} {highlight.message}")
        lines.append("")

    # Lift Progress Table
    if review.lift_progress:
        lines.append("## Lift Progress (Last 4 Weeks)")
        lines.append("")
        lines.append("| Lift | Current e1RM | 4wk Ago | Change | Trend |")
        lines.append("|------|-------------|---------|--------|-------|")

        for lift_id, progress in review.lift_progress.items():
            current = progress["current_e1rm"]
            prev = progress["e1rm_4wk_ago"]
            change = progress["change_pct"]
            trend = progress["trend"]

            change_str = f"+{change:.1f}%" if change > 0 else f"{change:.1f}%"
            trend_str = trend_emoji(trend)

            lines.append(
                f"| {format_lift_name(lift_id)} | {current:.0f} lb | {prev:.0f} lb | {change_str} | {trend_str} |"
            )
        lines.append("")

    # Volume by Muscle Group
    if review.muscle_volume:
        lines.append("## Volume Distribution")
        lines.append("")
        lines.append("| Muscle Group | Sets | Tonnage |")
        lines.append("|--------------|------|---------|")

        # Sort by sets descending
        sorted_muscles = sorted(
            review.muscle_volume.items(), key=lambda x: x[1]["sets"], reverse=True
        )
        for muscle, data in sorted_muscles[:8]:  # Top 8
            if data["sets"] > 0:
                lines.append(
                    f"| {muscle.title()} | {data['sets']} | {data['tonnage_lb']:,.0f} lb |"
                )
        lines.append("")

    # Intensity Distribution
    if review.intensity:
        lines.append("## Intensity Distribution")
        total = review.intensity.get("total_sets", 0)
        if total > 0:
            heavy = review.intensity.get("heavy", {})
            strength = review.intensity.get("strength", {})
            hypertrophy = review.intensity.get("hypertrophy", {})
            endurance = review.intensity.get("endurance", {})

            lines.append(f"- **Heavy (1-3 reps):** {heavy.get('pct', 0):.0f}%")
            lines.append(f"- **Strength (4-6 reps):** {strength.get('pct', 0):.0f}%")
            lines.append(f"- **Hypertrophy (7-12 reps):** {hypertrophy.get('pct', 0):.0f}%")
            lines.append(f"- **Endurance (13+ reps):** {endurance.get('pct', 0):.0f}%")
        lines.append("")

    # Body Composition
    if review.weight_data:
        lines.append("## Body Composition")
        wd = review.weight_data
        lines.append(f"- **Current Weight:** {wd['rolling_avg']:.1f} lb (7-day avg)")
        lines.append(f"- **Weekly Change:** {wd['weekly_change']:+.1f} lb")
        lines.append(f"- **4-Week Trend:** {wd['trend_4wk'].title()}")

        if review.recomp_signal and review.recomp_signal.get("is_likely"):
            lines.append(f"- **Signal:** {review.recomp_signal['explanation']}")

        if wd.get("alerts"):
            for alert in wd["alerts"]:
                lines.append(f"- **Alert:** {alert}")
        lines.append("")

    # Strength Percentiles
    if review.percentiles:
        lines.append("## Strength Percentiles")
        lines.append("")
        lines.append("| Lift | e1RM | BW Multiple | Percentile | Class |")
        lines.append("|------|------|-------------|------------|-------|")

        for lift_id, pct in review.percentiles.items():
            lines.append(
                f"| {format_lift_name(lift_id)} | {pct.e1rm_lb:.0f} lb | "
                f"{pct.bodyweight_multiple:.2f}x | {pct.percentile:.0f}th | {pct.classification} |"
            )
        lines.append("")

    # Recommendations
    if include_recommendations:
        recommendations = generate_all_recommendations(review)
        if recommendations:
            lines.append("---")
            lines.append("")
            lines.append("## Next Week Recommendations")
            lines.append("")

            # Group by category
            by_category: dict[str, list[Recommendation]] = {}
            for rec in recommendations:
                if rec.category not in by_category:
                    by_category[rec.category] = []
                by_category[rec.category].append(rec)

            category_order = ["training", "recovery", "nutrition", "general"]
            for category in category_order:
                if category in by_category:
                    lines.append(f"### {category.title()}")
                    for i, rec in enumerate(by_category[category][:3], 1):  # Top 3 per category
                        priority_marker = {"high": "(!)", "medium": "", "low": ""}.get(
                            rec.priority, ""
                        )
                        lines.append(f"{i}. **{rec.title}** {priority_marker}")
                        lines.append(f"   {rec.details}")
                        if rec.caveat:
                            lines.append(f"   *Note: {rec.caveat}*")
                    lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*Report generated {date.today().strftime('%b %d, %Y')} | Data source: local*")

    return "\n".join(lines)


def generate_lift_progress_markdown(
    lift_id: str,
    trend_data: dict,
    percentile_data: Optional[dict] = None,
) -> str:
    """Generate a detailed report for a single lift."""
    lines: list[str] = []

    lines.append(f"# {format_lift_name(lift_id)} Progress Report")
    lines.append("")

    # Current status
    lines.append("## Current Status")
    lines.append(f"- **Current e1RM:** {trend_data['current_e1rm']:.0f} lb")
    lines.append(f"- **4 Weeks Ago:** {trend_data['e1rm_n_weeks_ago']:.0f} lb")
    lines.append(f"- **Change:** {trend_data['e1rm_change_pct']:+.1f}%")
    lines.append(f"- **Trend:** {trend_data['trend_direction'].title()}")
    lines.append("")

    # Percentile if available
    if percentile_data:
        lines.append("## Strength Level")
        lines.append(f"- **Percentile:** {percentile_data['percentile']:.0f}th")
        lines.append(f"- **Classification:** {percentile_data['classification']}")
        lines.append(f"- **BW Multiple:** {percentile_data['bodyweight_multiple']:.2f}x")
        lines.append("")

    # Weekly history
    if trend_data.get("weekly_data"):
        lines.append("## Weekly Best e1RM")
        lines.append("")
        lines.append("| Week | Best e1RM | Weight x Reps |")
        lines.append("|------|-----------|---------------|")

        for week in trend_data["weekly_data"][-8:]:  # Last 8 weeks
            week_start = week["week_start"]
            if hasattr(week_start, "strftime"):
                week_str = week_start.strftime("%b %d")
            else:
                week_str = str(week_start)
            lines.append(
                f"| {week_str} | {week['best_e1rm']:.0f} lb | "
                f"{week['best_weight']:.0f} x {week['best_reps']} |"
            )
        lines.append("")

    return "\n".join(lines)
