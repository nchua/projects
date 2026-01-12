"""
Analytics API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import date, datetime, timedelta
from collections import defaultdict

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User, UserProfile
from app.models.workout import WorkoutSession, WorkoutExercise, Set
from app.models.exercise import Exercise
from app.models.pr import PR, PRType as PRTypeModel
from app.schemas.analytics import (
    TrendResponse, TrendDirection, DataPoint, TimeRange,
    ExerciseHistoryResponse, SetHistoryItem, SessionGroup,
    PercentilesResponse, ExercisePercentile, StrengthClassification,
    PRResponse, PRListResponse, PRType,
    InsightsResponse, Insight, InsightType, InsightPriority,
    WeeklyReviewResponse
)
from app.schemas.cooldown import CooldownResponse
from app.services.cooldown_service import calculate_cooldowns

router = APIRouter()


# Strength standards (bodyweight multipliers) for common exercises
# Based on symmetric strength and other strength standards databases
# Format: {sex: {exercise_canonical: {classification: multiplier}}}
STRENGTH_STANDARDS = {
    "male": {
        "squat": {"beginner": 0.75, "novice": 1.0, "intermediate": 1.5, "advanced": 2.0, "elite": 2.5},
        "bench": {"beginner": 0.5, "novice": 0.75, "intermediate": 1.25, "advanced": 1.5, "elite": 2.0},
        "deadlift": {"beginner": 1.0, "novice": 1.25, "intermediate": 1.75, "advanced": 2.5, "elite": 3.0},
        "overhead_press": {"beginner": 0.35, "novice": 0.55, "intermediate": 0.8, "advanced": 1.0, "elite": 1.35},
        "row": {"beginner": 0.4, "novice": 0.6, "intermediate": 0.9, "advanced": 1.2, "elite": 1.5},
    },
    "female": {
        "squat": {"beginner": 0.5, "novice": 0.75, "intermediate": 1.0, "advanced": 1.5, "elite": 2.0},
        "bench": {"beginner": 0.25, "novice": 0.5, "intermediate": 0.75, "advanced": 1.0, "elite": 1.25},
        "deadlift": {"beginner": 0.75, "novice": 1.0, "intermediate": 1.25, "advanced": 1.75, "elite": 2.25},
        "overhead_press": {"beginner": 0.2, "novice": 0.35, "intermediate": 0.5, "advanced": 0.65, "elite": 0.85},
        "row": {"beginner": 0.25, "novice": 0.4, "intermediate": 0.6, "advanced": 0.8, "elite": 1.0},
    }
}


TIME_RANGE_DAYS = {
    "4w": 28,
    "8w": 56,
    "12w": 84,
    "26w": 182,
    "52w": 365,
    "1y": 365,
}


def get_time_range_days(time_range: str) -> Optional[int]:
    """Convert time range string to number of days. Returns None for all time."""
    return TIME_RANGE_DAYS.get(time_range)


CANONICAL_EXERCISE_KEYWORDS = [
    ("overhead_press", ["press", "overhead"]),
    ("squat", ["squat"]),
    ("bench", ["bench"]),
    ("deadlift", ["deadlift"]),
    ("row", ["row"]),
]


def get_exercise_canonical_id(exercise_name: str) -> Optional[str]:
    """Get canonical ID for exercise name matching."""
    name_lower = exercise_name.lower()
    for canonical_id, keywords in CANONICAL_EXERCISE_KEYWORDS:
        if all(keyword in name_lower for keyword in keywords):
            return canonical_id
    return None


PERCENTILE_RANGES = [
    ("beginner", "novice", 20, 20, StrengthClassification.BEGINNER),
    ("novice", "intermediate", 40, 20, StrengthClassification.NOVICE),
    ("intermediate", "advanced", 60, 20, StrengthClassification.INTERMEDIATE),
    ("advanced", "elite", 80, 15, StrengthClassification.ADVANCED),
]


def calculate_percentile(bw_multiplier: float, standards: dict) -> tuple:
    """Calculate percentile and classification from bodyweight multiplier."""
    if bw_multiplier < standards["beginner"]:
        pct = int((bw_multiplier / standards["beginner"]) * 20)
        return max(1, pct), StrengthClassification.BEGINNER

    for lower_key, upper_key, base_pct, range_pct, classification in PERCENTILE_RANGES:
        if bw_multiplier < standards[upper_key]:
            range_size = standards[upper_key] - standards[lower_key]
            position = (bw_multiplier - standards[lower_key]) / range_size
            pct = base_pct + int(position * range_pct)
            return pct, classification

    # Elite (95th+ percentile)
    return min(99, 95 + int((bw_multiplier - standards["elite"]) * 5)), StrengthClassification.ELITE


@router.get("/exercise/{exercise_id}/trend", response_model=TrendResponse)
async def get_exercise_trend(
    exercise_id: str,
    time_range: str = Query("12w", description="Time range: 4w, 12w, 1y, all"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get e1RM trend data for an exercise.
    Aggregates data across all exercises with the same canonical_id.
    """
    # Verify exercise exists
    exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    # Find all exercise IDs with the same canonical_id (to aggregate variations)
    canonical_id = exercise.canonical_id or exercise.id
    related_exercises = db.query(Exercise.id).filter(
        (Exercise.canonical_id == canonical_id) | (Exercise.id == canonical_id)
    ).all()
    exercise_ids = [ex.id for ex in related_exercises] if related_exercises else [exercise_id]

    # Build date filter
    days = get_time_range_days(time_range)
    date_filter = []
    if days:
        start_date = date.today() - timedelta(days=days)
        date_filter.append(WorkoutSession.date >= start_date)

    # Query all sets for this exercise and its canonical variations
    query = db.query(Set, WorkoutSession.date).join(
        WorkoutExercise, Set.workout_exercise_id == WorkoutExercise.id
    ).join(
        WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id
    ).filter(
        WorkoutExercise.exercise_id.in_(exercise_ids),
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.deleted_at == None,
        *date_filter
    ).order_by(WorkoutSession.date).all()

    if not query:
        return TrendResponse(
            exercise_id=exercise_id,
            exercise_name=exercise.name,
            time_range=time_range,
            data_points=[],
            weekly_best_e1rm=[],
            trend_direction=TrendDirection.INSUFFICIENT_DATA,
            total_workouts=0
        )

    # Group by date and get best e1RM per day
    daily_best = {}
    for set_obj, workout_date in query:
        date_str = workout_date.isoformat()
        if date_str not in daily_best or set_obj.e1rm > daily_best[date_str]:
            daily_best[date_str] = set_obj.e1rm

    # Build data points
    data_points = [DataPoint(date=d, value=round(v, 2)) for d, v in sorted(daily_best.items())]

    # Calculate weekly best
    weekly_best = {}
    for date_str, e1rm in daily_best.items():
        week_start = datetime.fromisoformat(date_str).date()
        week_start = week_start - timedelta(days=week_start.weekday())
        week_key = week_start.isoformat()
        if week_key not in weekly_best or e1rm > weekly_best[week_key]:
            weekly_best[week_key] = e1rm

    weekly_best_points = [DataPoint(date=d, value=round(v, 2)) for d, v in sorted(weekly_best.items())]

    # Calculate rolling 4-week average
    rolling_avg = None
    if len(weekly_best_points) >= 4:
        recent_4_weeks = [p.value for p in weekly_best_points[-4:]]
        rolling_avg = round(sum(recent_4_weeks) / len(recent_4_weeks), 2)

    # Current e1RM (most recent)
    current_e1rm = data_points[-1].value if data_points else None

    # Calculate trend
    trend = TrendDirection.INSUFFICIENT_DATA
    percent_change = None
    if len(weekly_best_points) >= 4:
        first_half = [p.value for p in weekly_best_points[:len(weekly_best_points)//2]]
        second_half = [p.value for p in weekly_best_points[len(weekly_best_points)//2:]]
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)

        percent_change = round(((second_avg - first_avg) / first_avg) * 100, 1)

        if percent_change > 2:
            trend = TrendDirection.IMPROVING
        elif percent_change < -2:
            trend = TrendDirection.REGRESSING
        else:
            trend = TrendDirection.STABLE

    # Count unique workouts
    workout_dates = set(p.date for p in data_points)

    return TrendResponse(
        exercise_id=exercise_id,
        exercise_name=exercise.name,
        time_range=time_range,
        data_points=data_points,
        weekly_best_e1rm=weekly_best_points,
        rolling_average_4w=rolling_avg,
        current_e1rm=current_e1rm,
        trend_direction=trend,
        percent_change=percent_change,
        total_workouts=len(workout_dates)
    )


@router.get("/exercise/{exercise_id}/history", response_model=ExerciseHistoryResponse)
async def get_exercise_history(
    exercise_id: str,
    limit: int = Query(50, ge=1, le=200, description="Number of sessions to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get complete set history for an exercise
    """
    # Verify exercise exists
    exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    # Query workout exercises with sets
    workout_exercises = db.query(WorkoutExercise).options(
        joinedload(WorkoutExercise.sets),
        joinedload(WorkoutExercise.session)
    ).join(
        WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id
    ).filter(
        WorkoutExercise.exercise_id == exercise_id,
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.deleted_at == None
    ).order_by(desc(WorkoutSession.date)).limit(limit).all()

    # Group by session
    sessions = []
    total_sets = 0
    best_e1rm = 0
    best_volume_session = None
    best_volume = 0

    for we in workout_exercises:
        session_sets = []
        session_volume = 0

        for s in sorted(we.sets, key=lambda x: x.set_number):
            session_sets.append(SetHistoryItem(
                date=we.session.date.isoformat(),
                workout_id=we.session_id,
                weight=s.weight,
                reps=s.reps,
                rpe=s.rpe,
                rir=s.rir,
                e1rm=round(s.e1rm, 2) if s.e1rm else 0,
                set_number=s.set_number
            ))
            total_sets += 1
            session_volume += s.weight * s.reps
            if s.e1rm and s.e1rm > best_e1rm:
                best_e1rm = s.e1rm

        if session_sets:
            sessions.append(SessionGroup(
                workout_id=we.session_id,
                date=we.session.date.isoformat(),
                sets=session_sets
            ))
            if session_volume > best_volume:
                best_volume = session_volume
                best_volume_session = we.session_id

    return ExerciseHistoryResponse(
        exercise_id=exercise_id,
        exercise_name=exercise.name,
        sessions=sessions,
        total_sets=total_sets,
        best_e1rm=round(best_e1rm, 2) if best_e1rm else None,
        best_volume_session=best_volume_session
    )


@router.get("/percentiles", response_model=PercentilesResponse)
async def get_percentiles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Calculate strength percentiles for user's tracked exercises
    """
    # Get user profile
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    bodyweight = None
    age = None
    sex = "male"  # Default

    if profile:
        bodyweight = profile.bodyweight_lb
        age = profile.age
        if profile.sex:
            # profile.sex is "M" or "F", map to "male"/"female" for standards lookup
            sex = "male" if profile.sex == "M" else "female"

    # Get best e1RM for each tracked exercise
    subquery = db.query(
        WorkoutExercise.exercise_id,
        func.max(Set.e1rm).label("max_e1rm")
    ).join(
        Set, Set.workout_exercise_id == WorkoutExercise.id
    ).join(
        WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id
    ).filter(
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.deleted_at == None
    ).group_by(WorkoutExercise.exercise_id).subquery()

    # Join with exercises
    results = db.query(
        Exercise.id,
        Exercise.name,
        subquery.c.max_e1rm
    ).join(
        subquery, Exercise.id == subquery.c.exercise_id
    ).all()

    exercises = []
    standards = STRENGTH_STANDARDS.get(sex, STRENGTH_STANDARDS["male"])

    for exercise_id, exercise_name, max_e1rm in results:
        canonical_id = get_exercise_canonical_id(exercise_name)
        percentile = None
        classification = StrengthClassification.BEGINNER
        bw_multiplier = None

        if bodyweight and max_e1rm and canonical_id in standards:
            bw_multiplier = round(max_e1rm / bodyweight, 2)
            percentile, classification = calculate_percentile(bw_multiplier, standards[canonical_id])

        exercises.append(ExercisePercentile(
            exercise_id=exercise_id,
            exercise_name=exercise_name,
            current_e1rm=round(max_e1rm, 2) if max_e1rm else None,
            bodyweight_multiplier=bw_multiplier,
            percentile=percentile,
            classification=classification
        ))

    return PercentilesResponse(
        user_bodyweight=bodyweight,
        user_age=age,
        user_sex=sex,
        exercises=exercises
    )


def get_canonical_exercise_name(db: Session, canonical_id: str) -> str:
    """Get the primary name for a canonical exercise group (the first seeded exercise)"""
    primary = db.query(Exercise).filter(
        Exercise.canonical_id == canonical_id,
        Exercise.is_custom == False
    ).order_by(Exercise.created_at).first()
    return primary.name if primary else "Unknown"


@router.get("/prs", response_model=PRListResponse)
async def get_prs(
    exercise_id: Optional[str] = Query(None, description="Filter by exercise"),
    pr_type: Optional[str] = Query(None, description="Filter by type: e1rm or rep_pr"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    group_by_canonical: bool = Query(True, description="Group PRs by canonical exercise"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all PRs for user with filtering options.
    When group_by_canonical=True, returns only the best PR per canonical exercise per type.
    """
    query = db.query(PR).options(
        joinedload(PR.exercise)
    ).filter(PR.user_id == current_user.id)

    if exercise_id:
        query = query.filter(PR.exercise_id == exercise_id)

    if pr_type:
        if pr_type == "e1rm":
            query = query.filter(PR.pr_type == PRTypeModel.E1RM)
        elif pr_type == "rep_pr":
            query = query.filter(PR.pr_type == PRTypeModel.REP_PR)

    if start_date:
        query = query.filter(PR.achieved_at >= datetime.combine(start_date, datetime.min.time()))

    if end_date:
        query = query.filter(PR.achieved_at <= datetime.combine(end_date, datetime.max.time()))

    # Get all matching PRs
    all_prs = query.order_by(desc(PR.achieved_at)).all()

    if group_by_canonical:
        # Group PRs by (canonical_id, pr_type) and keep only the best
        best_prs = {}
        for pr in all_prs:
            if not pr.exercise:
                continue

            canonical_id = pr.exercise.canonical_id or pr.exercise_id
            key = (canonical_id, pr.pr_type)

            if key not in best_prs:
                best_prs[key] = pr
            else:
                existing = best_prs[key]
                # For e1rm: keep the one with highest value
                if pr.pr_type == PRTypeModel.E1RM:
                    if pr.value and (not existing.value or pr.value > existing.value):
                        best_prs[key] = pr
                # For rep_pr: keep the one with highest weight (most impressive)
                else:
                    if pr.weight and (not existing.weight or pr.weight > existing.weight):
                        best_prs[key] = pr

        # Sort by achieved_at descending
        prs = sorted(best_prs.values(), key=lambda p: p.achieved_at, reverse=True)
        total_count = len(prs)

        # Apply pagination
        prs = prs[offset:offset + limit]
    else:
        total_count = query.count()
        prs = all_prs[offset:offset + limit]

    pr_responses = []
    for pr in prs:
        canonical_id = pr.exercise.canonical_id if pr.exercise else None
        canonical_name = get_canonical_exercise_name(db, canonical_id) if canonical_id else None

        pr_responses.append(PRResponse(
            id=pr.id,
            exercise_id=pr.exercise_id,
            exercise_name=pr.exercise.name if pr.exercise else "Unknown",
            canonical_id=canonical_id,
            canonical_exercise_name=canonical_name,
            pr_type=PRType.E1RM if pr.pr_type == PRTypeModel.E1RM else PRType.REP_PR,
            value=round(pr.value, 2) if pr.value else None,
            reps=pr.reps,
            weight=round(pr.weight, 2) if pr.weight else None,
            achieved_at=pr.achieved_at.isoformat(),
            created_at=pr.created_at.isoformat()
        ))

    return PRListResponse(prs=pr_responses, total_count=total_count)


@router.get("/insights", response_model=InsightsResponse)
async def get_insights(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate personalized workout insights
    """
    insights = []
    four_weeks_ago = date.today() - timedelta(days=28)

    # Get recent workout data
    recent_workouts = db.query(WorkoutSession).filter(
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.deleted_at == None,
        WorkoutSession.date >= four_weeks_ago
    ).all()

    if not recent_workouts:
        insights.append(Insight(
            type=InsightType.VOLUME_LOW,
            priority=InsightPriority.HIGH,
            title="No recent workouts",
            description="You haven't logged any workouts in the last 4 weeks. Time to get back to training!"
        ))
        return InsightsResponse(insights=insights, generated_at=datetime.utcnow().isoformat())

    # Analyze exercise trends - aggregate by date using max e1RM per workout
    # This prevents false alerts from within-session fatigue (later sets have lower e1RM)
    exercise_data = defaultdict(dict)  # {exercise_id: {date: {"e1rm": max_e1rm, "exercise_name": name}}}
    for workout in recent_workouts:
        for we in workout.workout_exercises:
            best_e1rm = max((s.e1rm for s in we.sets if s.e1rm), default=None)
            if best_e1rm:
                exercise_id = we.exercise_id
                workout_date = workout.date
                exercise_name = we.exercise.name if we.exercise else "Unknown"

                # Keep only the best e1RM per exercise per date
                if workout_date not in exercise_data[exercise_id] or \
                   best_e1rm > exercise_data[exercise_id][workout_date]["e1rm"]:
                    exercise_data[exercise_id][workout_date] = {
                        "e1rm": best_e1rm,
                        "exercise_name": exercise_name
                    }

    # Convert to list format for analysis
    exercise_trends = {}
    for exercise_id, date_data in exercise_data.items():
        exercise_trends[exercise_id] = [
            {"date": d, "e1rm": data["e1rm"], "exercise_name": data["exercise_name"]}
            for d, data in date_data.items()
        ]

    # Find improving and regressing exercises
    # Require at least 4 distinct workout dates for meaningful trend analysis
    MIN_WORKOUTS_FOR_TREND = 4
    for exercise_id, data in exercise_trends.items():
        if len(data) < MIN_WORKOUTS_FOR_TREND:
            continue

        sorted_data = sorted(data, key=lambda x: x["date"])
        mid = len(sorted_data) // 2
        first_half_avg = sum(d["e1rm"] for d in sorted_data[:mid]) / mid
        second_half_avg = sum(d["e1rm"] for d in sorted_data[mid:]) / len(sorted_data[mid:])

        percent_change = ((second_half_avg - first_half_avg) / first_half_avg) * 100
        exercise_name = sorted_data[0]["exercise_name"]

        if percent_change > 5:
            insights.append(Insight(
                type=InsightType.IMPROVING,
                priority=InsightPriority.LOW,
                title=f"{exercise_name} is improving!",
                description=f"Your e1RM has increased {percent_change:.1f}% over the last 4 weeks.",
                exercise_id=exercise_id,
                exercise_name=exercise_name,
                data={"percent_change": round(percent_change, 1)}
            ))
        elif percent_change < -5:
            insights.append(Insight(
                type=InsightType.REGRESSING,
                priority=InsightPriority.MEDIUM,
                title=f"{exercise_name} needs attention",
                description=f"Your e1RM has decreased {abs(percent_change):.1f}% over the last 4 weeks. Consider reviewing your programming.",
                exercise_id=exercise_id,
                exercise_name=exercise_name,
                data={"percent_change": round(percent_change, 1)}
            ))
        elif len(data) > 8 and abs(percent_change) < 2:
            insights.append(Insight(
                type=InsightType.PLATEAU,
                priority=InsightPriority.MEDIUM,
                title=f"{exercise_name} has plateaued",
                description="Your progress has stalled. Consider changing rep ranges, adding variations, or deloading.",
                exercise_id=exercise_id,
                exercise_name=exercise_name
            ))

    # Check workout frequency
    workouts_per_week = len(recent_workouts) / 4
    if workouts_per_week < 2:
        insights.append(Insight(
            type=InsightType.VOLUME_LOW,
            priority=InsightPriority.HIGH,
            title="Low training frequency",
            description=f"You're averaging {workouts_per_week:.1f} workouts per week. Aim for 3-4 sessions for optimal progress.",
            data={"workouts_per_week": round(workouts_per_week, 1)}
        ))
    elif workouts_per_week > 6:
        insights.append(Insight(
            type=InsightType.VOLUME_HIGH,
            priority=InsightPriority.MEDIUM,
            title="High training frequency",
            description=f"You're averaging {workouts_per_week:.1f} workouts per week. Make sure you're recovering adequately.",
            data={"workouts_per_week": round(workouts_per_week, 1)}
        ))

    # Sort by priority
    priority_order = {InsightPriority.HIGH: 0, InsightPriority.MEDIUM: 1, InsightPriority.LOW: 2}
    insights.sort(key=lambda x: priority_order[x.priority])

    return InsightsResponse(insights=insights, generated_at=datetime.utcnow().isoformat())


@router.get("/weekly-review", response_model=WeeklyReviewResponse)
async def get_weekly_review(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate comprehensive weekly summary
    """
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start - timedelta(days=1)

    # This week's workouts
    this_week = db.query(WorkoutSession).options(
        joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets)
    ).filter(
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.deleted_at == None,
        WorkoutSession.date >= week_start,
        WorkoutSession.date <= week_end
    ).all()

    # Last week's workouts
    last_week = db.query(WorkoutSession).options(
        joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets)
    ).filter(
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.deleted_at == None,
        WorkoutSession.date >= prev_week_start,
        WorkoutSession.date <= prev_week_end
    ).all()

    # Calculate this week's stats
    total_workouts = len(this_week)
    total_sets = 0
    total_volume = 0
    exercise_e1rms = defaultdict(list)

    for workout in this_week:
        for we in workout.workout_exercises:
            for s in we.sets:
                total_sets += 1
                total_volume += s.weight * s.reps
                if s.e1rm:
                    exercise_e1rms[we.exercise_id].append({
                        "e1rm": s.e1rm,
                        "name": we.exercise.name if we.exercise else "Unknown"
                    })

    # Calculate last week's volume for comparison
    last_week_volume = 0
    last_week_e1rms = defaultdict(list)
    for workout in last_week:
        for we in workout.workout_exercises:
            for s in we.sets:
                last_week_volume += s.weight * s.reps
                if s.e1rm:
                    last_week_e1rms[we.exercise_id].append(s.e1rm)

    volume_change = None
    if last_week_volume > 0:
        volume_change = round(((total_volume - last_week_volume) / last_week_volume) * 100, 1)

    # Find fastest improving exercise
    fastest_improving = None
    fastest_percent = 0
    regressing = []

    for ex_id, this_week_data in exercise_e1rms.items():
        if ex_id in last_week_e1rms:
            this_avg = sum(d["e1rm"] for d in this_week_data) / len(this_week_data)
            last_avg = sum(last_week_e1rms[ex_id]) / len(last_week_e1rms[ex_id])
            pct_change = ((this_avg - last_avg) / last_avg) * 100

            if pct_change > fastest_percent:
                fastest_percent = pct_change
                fastest_improving = this_week_data[0]["name"]
            elif pct_change < -5:
                regressing.append(this_week_data[0]["name"])

    # Get PRs from this week
    week_prs = db.query(PR).options(joinedload(PR.exercise)).filter(
        PR.user_id == current_user.id,
        PR.achieved_at >= datetime.combine(week_start, datetime.min.time()),
        PR.achieved_at <= datetime.combine(week_end, datetime.max.time())
    ).order_by(desc(PR.achieved_at)).all()

    pr_responses = [
        PRResponse(
            id=pr.id,
            exercise_id=pr.exercise_id,
            exercise_name=pr.exercise.name,
            pr_type=PRType.E1RM if pr.pr_type == PRTypeModel.E1RM else PRType.REP_PR,
            value=round(pr.value, 2) if pr.value else None,
            reps=pr.reps,
            weight=round(pr.weight, 2) if pr.weight else None,
            achieved_at=pr.achieved_at.isoformat(),
            created_at=pr.created_at.isoformat()
        )
        for pr in week_prs
    ]

    # Generate insights
    insights = []
    if total_workouts == 0:
        insights.append(Insight(
            type=InsightType.VOLUME_LOW,
            priority=InsightPriority.HIGH,
            title="No workouts this week",
            description="You haven't logged any workouts this week yet."
        ))
    elif len(week_prs) > 0:
        insights.append(Insight(
            type=InsightType.PR_STREAK,
            priority=InsightPriority.LOW,
            title=f"Hit {len(week_prs)} PR{'s' if len(week_prs) > 1 else ''} this week!",
            description="Great progress! Keep pushing."
        ))

    return WeeklyReviewResponse(
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        total_workouts=total_workouts,
        total_sets=total_sets,
        total_volume=round(total_volume, 2),
        prs_achieved=pr_responses,
        volume_change_percent=volume_change,
        fastest_improving_exercise=fastest_improving if fastest_percent > 0 else None,
        fastest_improving_percent=round(fastest_percent, 1) if fastest_percent > 0 else None,
        regressing_exercises=regressing,
        insights=insights
    )


@router.get("/cooldowns", response_model=CooldownResponse)
async def get_cooldown_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get muscle cooldown status for the current user.

    Returns only muscle groups that are currently cooling down.
    Each muscle group includes:
    - cooldown_percent: 0-100% (100 = fully ready)
    - hours_remaining: hours until fully ready
    - affected_exercises: list of exercises that caused the fatigue

    Cooldown times are science-based:
    - Large muscles (Chest, Hamstrings): 72 hours
    - Medium muscles (Quads, Shoulders): 48 hours
    - Small muscles (Biceps, Triceps): 36 hours

    Compound exercises transfer fatigue:
    - Primary muscles: 100% fatigue
    - Secondary muscles: 50% fatigue

    Age-based modifiers:
    - Under 30: 1.0x baseline
    - 30-40: 1.15x baseline
    - 40-50: 1.3x baseline
    - 50+: 1.5x baseline
    """
    # Fetch user profile to get age for cooldown modifier
    user_profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    user_age = user_profile.age if user_profile else None

    cooldown_data = calculate_cooldowns(db, current_user.id, user_age=user_age)
    return CooldownResponse(**cooldown_data)
