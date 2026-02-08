"""
Weekly Progress Report service — goal-vs-actual comparison with pace prediction
and actionable coaching suggestions.
"""
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from collections import defaultdict

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from app.core.utils import to_iso8601_utc
from app.models.workout import WorkoutSession, WorkoutExercise, Set
from app.models.exercise import Exercise
from app.models.mission import Goal, GoalProgressSnapshot, GoalStatus
from app.models.pr import PR, PRType as PRTypeModel
from app.schemas.analytics import PRResponse, PRType
from app.schemas.weekly_report import (
    GoalProgressReport,
    CoachingSuggestion,
    WeeklyProgressReportResponse,
    PaceStatus,
    SuggestionType,
    SuggestionPriority,
)
from app.schemas.mission import ProgressPoint
from app.services.mission_service import get_goal_progress_data


def generate_weekly_report(
    db: Session,
    user_id: str,
    week_start: Optional[date] = None,
) -> WeeklyProgressReportResponse:
    """Generate the full weekly progress report."""
    today = date.today()
    if week_start is None:
        week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start - timedelta(days=1)

    # 1. Workout summary (this week + last week for comparison)
    summary = _get_weekly_workout_summary(
        db, user_id, week_start, week_end, prev_week_start, prev_week_end
    )

    # 2. PRs this week
    prs = _get_week_prs(db, user_id, week_start, week_end)

    # 3. Goal progress reports
    goal_reports = _get_goal_progress_reports(db, user_id)

    # 4. Exercise-level weekly sets count (for suggestions)
    exercise_sets = _get_exercise_weekly_sets(db, user_id, week_start, week_end)

    # 5. Coaching suggestions
    suggestions = _generate_suggestions(goal_reports, summary, exercise_sets)

    # Determine if we have enough historical data (>= 2 weeks of workouts)
    two_weeks_ago = week_start - timedelta(days=14)
    older_count = (
        db.query(WorkoutSession)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at == None,
            WorkoutSession.date >= two_weeks_ago,
            WorkoutSession.date < week_start,
        )
        .count()
    )
    has_sufficient_data = older_count >= 2

    return WeeklyProgressReportResponse(
        week_start=to_iso8601_utc(week_start),
        week_end=to_iso8601_utc(week_end),
        total_workouts=summary["total_workouts"],
        total_sets=summary["total_sets"],
        total_volume=round(summary["total_volume"], 2),
        volume_change_percent=summary["volume_change_percent"],
        prs_achieved=prs,
        goal_reports=goal_reports,
        suggestions=suggestions,
        has_sufficient_data=has_sufficient_data,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_weekly_workout_summary(
    db: Session,
    user_id: str,
    week_start: date,
    week_end: date,
    prev_week_start: date,
    prev_week_end: date,
) -> Dict[str, Any]:
    """Compute workouts/sets/volume for this week and volume change vs last week."""
    this_week = (
        db.query(WorkoutSession)
        .options(
            joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets)
        )
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at == None,
            WorkoutSession.date >= week_start,
            WorkoutSession.date <= week_end,
        )
        .all()
    )

    total_workouts = len(this_week)
    total_sets = 0
    total_volume = 0.0
    for w in this_week:
        for we in w.workout_exercises:
            for s in we.sets:
                total_sets += 1
                total_volume += s.weight * s.reps

    # Last week volume for comparison
    last_week = (
        db.query(WorkoutSession)
        .options(
            joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets)
        )
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at == None,
            WorkoutSession.date >= prev_week_start,
            WorkoutSession.date <= prev_week_end,
        )
        .all()
    )
    last_week_volume = 0.0
    for w in last_week:
        for we in w.workout_exercises:
            for s in we.sets:
                last_week_volume += s.weight * s.reps

    volume_change = None
    if last_week_volume > 0:
        volume_change = round(
            ((total_volume - last_week_volume) / last_week_volume) * 100, 1
        )

    return {
        "total_workouts": total_workouts,
        "total_sets": total_sets,
        "total_volume": total_volume,
        "volume_change_percent": volume_change,
    }


def _get_week_prs(
    db: Session, user_id: str, week_start: date, week_end: date
) -> List[PRResponse]:
    """Fetch PRs achieved during the given week."""
    week_prs = (
        db.query(PR)
        .options(joinedload(PR.exercise))
        .filter(
            PR.user_id == user_id,
            PR.achieved_at >= datetime.combine(week_start, datetime.min.time()),
            PR.achieved_at <= datetime.combine(week_end, datetime.max.time()),
        )
        .order_by(desc(PR.achieved_at))
        .all()
    )
    return [
        PRResponse(
            id=pr.id,
            exercise_id=pr.exercise_id,
            exercise_name=pr.exercise.name,
            pr_type=PRType.E1RM if pr.pr_type == PRTypeModel.E1RM else PRType.REP_PR,
            value=round(pr.value, 2) if pr.value else None,
            reps=pr.reps,
            weight=round(pr.weight, 2) if pr.weight else None,
            achieved_at=to_iso8601_utc(pr.achieved_at),
            created_at=to_iso8601_utc(pr.created_at),
        )
        for pr in week_prs
    ]


def _get_goal_progress_reports(
    db: Session, user_id: str
) -> List[GoalProgressReport]:
    """Build a progress report for each active goal."""
    goals = (
        db.query(Goal)
        .options(joinedload(Goal.exercise), joinedload(Goal.progress_snapshots))
        .filter(Goal.user_id == user_id, Goal.status == GoalStatus.ACTIVE.value)
        .all()
    )

    reports: List[GoalProgressReport] = []
    today = date.today()

    for goal in goals:
        starting = goal.starting_e1rm or 0
        current = goal.current_e1rm or starting
        from app.core.e1rm import calculate_e1rm
        target_e1rm = calculate_e1rm(goal.target_weight, goal.target_reps)

        total_range = target_e1rm - starting if target_e1rm != starting else 1
        progress_pct = max(0.0, min(100.0, ((current - starting) / total_range) * 100))

        days_remaining = (goal.deadline - today).days
        weeks_remaining = max(days_remaining / 7.0, 0)

        required_weekly_gain: Optional[float] = None
        if weeks_remaining > 0:
            required_weekly_gain = round((target_e1rm - current) / weeks_remaining, 2)

        # Calculate actual weekly gain from snapshots (last 4 weeks)
        actual_weekly_gain = _calc_actual_weekly_gain(goal.progress_snapshots)

        # Pace status
        status = _calculate_pace_status(required_weekly_gain, actual_weekly_gain, progress_pct)

        # Projected completion
        projected_date: Optional[str] = None
        if actual_weekly_gain and actual_weekly_gain > 0 and current < target_e1rm:
            weeks_to_go = (target_e1rm - current) / actual_weekly_gain
            proj = today + timedelta(weeks=weeks_to_go)
            projected_date = to_iso8601_utc(proj)

        # Graph data: reuse existing progress data generator
        progress_data = get_goal_progress_data(db, goal)
        actual_pts = [
            ProgressPoint(date=p["date"], e1rm=p["e1rm"])
            for p in progress_data.get("actual_points", [])
        ]
        projected_pts = [
            ProgressPoint(date=p["date"], e1rm=p["e1rm"])
            for p in progress_data.get("projected_points", [])
        ]

        reports.append(
            GoalProgressReport(
                goal_id=goal.id,
                exercise_name=goal.exercise.name if goal.exercise else "Unknown",
                exercise_id=goal.exercise_id,
                target_weight=goal.target_weight,
                target_reps=goal.target_reps,
                weight_unit=goal.weight_unit,
                deadline=to_iso8601_utc(goal.deadline),
                starting_e1rm=starting,
                current_e1rm=current,
                progress_percent=round(progress_pct, 1),
                required_weekly_gain=required_weekly_gain,
                actual_weekly_gain=round(actual_weekly_gain, 2) if actual_weekly_gain else None,
                status=status,
                projected_completion_date=projected_date,
                weeks_remaining=round(weeks_remaining, 1),
                actual_points=actual_pts,
                projected_points=projected_pts,
            )
        )
    return reports


def _calc_actual_weekly_gain(
    snapshots: list,
) -> Optional[float]:
    """Average weekly e1RM gain over the last 4 weeks from snapshots."""
    if len(snapshots) < 2:
        return None

    # Sort by date ascending
    sorted_snaps = sorted(snapshots, key=lambda s: s.recorded_at)

    # Only look at last 4 weeks of snapshots
    four_weeks_ago = datetime.utcnow() - timedelta(weeks=4)
    recent = [s for s in sorted_snaps if s.recorded_at >= four_weeks_ago]

    if len(recent) < 2:
        # Fall back to all snapshots if not enough recent ones
        recent = sorted_snaps

    if len(recent) < 2:
        return None

    first = recent[0]
    last = recent[-1]
    e1rm_delta = last.e1rm - first.e1rm
    days_delta = (last.recorded_at - first.recorded_at).days
    if days_delta <= 0:
        return None

    weekly_gain = e1rm_delta / (days_delta / 7.0)
    return weekly_gain


def _calculate_pace_status(
    required_weekly_gain: Optional[float],
    actual_weekly_gain: Optional[float],
    progress_pct: float,
) -> PaceStatus:
    """Determine if the user is on track, ahead, or behind."""
    # Already completed
    if progress_pct >= 100:
        return PaceStatus.AHEAD

    if required_weekly_gain is None or actual_weekly_gain is None:
        return PaceStatus.ON_TRACK  # Not enough data to judge

    if required_weekly_gain <= 0:
        # Deadline passed or target already met
        return PaceStatus.BEHIND if progress_pct < 100 else PaceStatus.AHEAD

    ratio = actual_weekly_gain / required_weekly_gain
    if ratio >= 1.2:
        return PaceStatus.AHEAD
    elif ratio >= 0.8:
        return PaceStatus.ON_TRACK
    else:
        return PaceStatus.BEHIND


def _get_exercise_weekly_sets(
    db: Session, user_id: str, week_start: date, week_end: date
) -> Dict[str, int]:
    """Count sets per exercise_id for this week."""
    workouts = (
        db.query(WorkoutSession)
        .options(
            joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets)
        )
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at == None,
            WorkoutSession.date >= week_start,
            WorkoutSession.date <= week_end,
        )
        .all()
    )
    counts: Dict[str, int] = defaultdict(int)
    for w in workouts:
        for we in w.workout_exercises:
            counts[we.exercise_id] += len(we.sets)
    return counts


def _generate_suggestions(
    goal_reports: List[GoalProgressReport],
    summary: Dict[str, Any],
    exercise_sets: Dict[str, int],
) -> List[CoachingSuggestion]:
    """Generate actionable coaching suggestions based on goal reports and weekly data."""
    suggestions: List[CoachingSuggestion] = []

    # No goals → suggest creating one
    if not goal_reports:
        suggestions.append(
            CoachingSuggestion(
                type=SuggestionType.MOTIVATION,
                priority=SuggestionPriority.MEDIUM,
                title="Set a strength goal",
                description="Create a goal to get personalized weekly progress tracking and coaching suggestions.",
            )
        )
        return suggestions

    # No workouts this week
    if summary["total_workouts"] == 0:
        suggestions.append(
            CoachingSuggestion(
                type=SuggestionType.FREQUENCY,
                priority=SuggestionPriority.HIGH,
                title="No workouts logged this week",
                description="Get back on track — even one session keeps momentum going.",
            )
        )
        return suggestions

    for report in goal_reports:
        sets_this_week = exercise_sets.get(report.exercise_id, 0)

        # Behind pace + low volume
        if report.status == PaceStatus.BEHIND and sets_this_week < 5:
            suggestions.append(
                CoachingSuggestion(
                    type=SuggestionType.VOLUME,
                    priority=SuggestionPriority.HIGH,
                    title=f"Increase {report.exercise_name} volume",
                    description=f"You're behind pace with only {sets_this_week} sets this week. Try adding 2-3 more sets to accelerate progress.",
                    exercise_name=report.exercise_name,
                )
            )

        # Plateau: no e1RM change with decent volume (check via actual_weekly_gain ≈ 0)
        if (
            report.actual_weekly_gain is not None
            and abs(report.actual_weekly_gain) < 0.5
            and sets_this_week >= 5
        ):
            suggestions.append(
                CoachingSuggestion(
                    type=SuggestionType.PLATEAU,
                    priority=SuggestionPriority.MEDIUM,
                    title=f"{report.exercise_name} plateau detected",
                    description="Your e1RM hasn't moved recently despite consistent volume. Try varying rep ranges or adding paused reps to break through.",
                    exercise_name=report.exercise_name,
                )
            )

        # Low frequency on compound + behind
        if report.status == PaceStatus.BEHIND and sets_this_week > 0 and sets_this_week <= 3:
            suggestions.append(
                CoachingSuggestion(
                    type=SuggestionType.FREQUENCY,
                    priority=SuggestionPriority.MEDIUM,
                    title=f"Train {report.exercise_name} more often",
                    description=f"You hit {report.exercise_name} once this week. Consider adding a second session to boost progress.",
                    exercise_name=report.exercise_name,
                )
            )

        # Ahead of schedule
        if report.status == PaceStatus.AHEAD:
            suggestions.append(
                CoachingSuggestion(
                    type=SuggestionType.MOTIVATION,
                    priority=SuggestionPriority.LOW,
                    title=f"Great progress on {report.exercise_name}!",
                    description="You're ahead of pace — keep it up!",
                    exercise_name=report.exercise_name,
                )
            )

        # Expected slowdown (>80% progress toward target)
        if report.progress_percent >= 80 and report.status != PaceStatus.AHEAD:
            suggestions.append(
                CoachingSuggestion(
                    type=SuggestionType.SLOWDOWN,
                    priority=SuggestionPriority.LOW,
                    title=f"Approaching {report.exercise_name} target",
                    description="Progress may slow as you get closer to your target — this is normal. Stay consistent.",
                    exercise_name=report.exercise_name,
                )
            )

    # Sort by priority
    priority_order = {
        SuggestionPriority.HIGH: 0,
        SuggestionPriority.MEDIUM: 1,
        SuggestionPriority.LOW: 2,
    }
    suggestions.sort(key=lambda s: priority_order[s.priority])

    return suggestions
