"""Build context prompts for LLM interactions."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from ..models import UserProfile, DEFAULT_USER_PROFILE
from ..storage import StorageBackend
from ..analytics import get_exercise_trend, build_pr_history
from ..percentiles import default_provider
from ..recomp import analyze_weight_trends, detect_recomp_signal
from ..reporting import generate_weekly_review
from .persona import CoachPersona, DEFAULT_PERSONA


def build_user_context(
    user_profile: Optional[UserProfile] = None,
) -> str:
    """Build user profile context string."""
    profile = user_profile or DEFAULT_USER_PROFILE

    lines = [
        "## User Profile",
        f"- Sex: {profile.sex}",
        f"- Age: {profile.age}",
        f"- Height: {profile.height_inches} inches",
        f"- Default bodyweight: {profile.default_bodyweight_lb} lb",
    ]

    if profile.training_years:
        lines.append(f"- Training experience: {profile.training_years:.1f} years")

    return "\n".join(lines)


def build_recent_training_context(
    storage: StorageBackend,
    weeks: int = 4,
) -> str:
    """Build context about recent training."""
    end_date = date.today()
    start_date = end_date - timedelta(weeks=weeks)

    sessions = storage.get_sessions(start_date=start_date, end_date=end_date)

    if not sessions:
        return "## Recent Training\nNo training data in the past 4 weeks."

    lines = ["## Recent Training (Last 4 Weeks)"]
    lines.append(f"- Sessions: {len(sessions)}")

    total_sets = sum(s.total_sets for s in sessions)
    total_volume = sum(float(s.total_volume_lb) for s in sessions)
    lines.append(f"- Total sets: {total_sets}")
    lines.append(f"- Total volume: {total_volume:,.0f} lb")

    # Exercise frequency
    exercise_counts: dict[str, int] = {}
    for session in sessions:
        for ex in session.exercises:
            ex_id = ex.canonical_id or ex.exercise_name
            exercise_counts[ex_id] = exercise_counts.get(ex_id, 0) + 1

    top_exercises = sorted(exercise_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    if top_exercises:
        lines.append("\nMost frequent exercises:")
        for ex, count in top_exercises:
            lines.append(f"  - {ex}: {count} sessions")

    return "\n".join(lines)


def build_lift_progress_context(
    storage: StorageBackend,
    lifts: Optional[list[str]] = None,
) -> str:
    """Build context about progress on main lifts."""
    if lifts is None:
        lifts = ["squat", "bench_press", "deadlift", "overhead_press"]

    lines = ["## Lift Progress"]

    for lift in lifts:
        history = storage.get_exercise_history(lift)
        if not history:
            continue

        trend = get_exercise_trend(history)

        if trend["current_e1rm"] > 0:
            lines.append(f"\n### {lift.replace('_', ' ').title()}")
            lines.append(f"- Current e1RM: {trend['current_e1rm']:.0f} lb")
            lines.append(f"- 4 weeks ago: {trend['e1rm_n_weeks_ago']:.0f} lb")
            lines.append(f"- Change: {trend['e1rm_change_pct']:+.1f}%")
            lines.append(f"- Trend: {trend['trend_direction']}")

    if len(lines) == 1:
        lines.append("No data for main lifts.")

    return "\n".join(lines)


def build_bodyweight_context(
    storage: StorageBackend,
    weeks: int = 4,
) -> str:
    """Build context about body weight trends."""
    entries = storage.get_bodyweight_entries(
        start_date=date.today() - timedelta(weeks=weeks)
    )

    if not entries:
        return "## Body Weight\nNo weight data available."

    analysis = analyze_weight_trends(entries)

    lines = ["## Body Weight"]
    lines.append(f"- Current: {analysis.current_weight:.1f} lb")
    lines.append(f"- 7-day average: {analysis.rolling_7day_avg:.1f} lb")
    lines.append(f"- Weekly change: {analysis.weekly_change_lb:+.1f} lb")
    lines.append(f"- 4-week trend: {analysis.trend_4wk}")

    if analysis.days_at_plateau > 0:
        lines.append(f"- Plateau: {analysis.days_at_plateau} days")

    if analysis.alerts:
        lines.append("\nAlerts:")
        for alert in analysis.alerts:
            lines.append(f"  - {alert}")

    return "\n".join(lines)


def build_percentile_context(
    storage: StorageBackend,
    user_profile: Optional[UserProfile] = None,
) -> str:
    """Build context about strength percentiles."""
    profile = user_profile or DEFAULT_USER_PROFILE

    # Get current bodyweight
    latest_weight = storage.get_latest_bodyweight()
    bodyweight = (
        latest_weight.weight_lb if latest_weight else profile.default_bodyweight_lb
    )

    lifts = ["squat", "bench_press", "deadlift", "overhead_press"]
    lines = ["## Strength Percentiles"]

    for lift in lifts:
        history = storage.get_exercise_history(lift)
        if not history:
            continue

        trend = get_exercise_trend(history)
        if trend["current_e1rm"] <= 0:
            continue

        try:
            pct = default_provider.get_percentile(
                lift, trend["current_e1rm"], bodyweight, profile.sex, profile.age
            )
            lines.append(
                f"- {lift.replace('_', ' ').title()}: "
                f"{pct.percentile:.0f}th percentile ({pct.classification})"
            )
        except ValueError:
            pass

    if len(lines) == 1:
        lines.append("No percentile data available.")

    return "\n".join(lines)


def build_full_context(
    storage: StorageBackend,
    user_profile: Optional[UserProfile] = None,
    include_percentiles: bool = True,
) -> str:
    """Build complete context for LLM query."""
    sections = [
        build_user_context(user_profile),
        build_recent_training_context(storage),
        build_lift_progress_context(storage),
        build_bodyweight_context(storage),
    ]

    if include_percentiles:
        sections.append(build_percentile_context(storage, user_profile))

    return "\n\n".join(sections)


def build_query_prompt(
    query: str,
    context: str,
    persona: Optional[CoachPersona] = None,
) -> str:
    """
    Build a complete prompt for answering a user query.

    Args:
        query: User's question
        context: Training context from build_full_context
        persona: Coach persona for response style

    Returns:
        Complete prompt for LLM
    """
    coach = persona or DEFAULT_PERSONA

    return f"""{coach.get_system_prompt()}

---

{context}

---

User Question: {query}

Respond based on the data above. If the data is insufficient to answer, say so clearly."""


# Example queries the system can handle
SUPPORTED_QUERIES = [
    "Am I getting stronger?",
    "Which lift is lagging?",
    "Should I deload?",
    "What's my estimated percentile?",
    "Am I eating enough?",
    "How has my squat progressed?",
    "What should I focus on next week?",
    "Am I overtraining?",
    "Is my volume appropriate?",
    "Should I cut or bulk?",
]
