"""
Workout API endpoints
"""
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.e1rm import (
    calculate_e1rm,
    calculate_e1rm_from_rir,
    calculate_e1rm_from_rpe,
    get_user_e1rm_formula,
)
from app.core.exertion import compute_arise_strain, compute_exertion_score
from app.core.utils import to_iso8601_utc
from app.models.exercise import Exercise
from app.models.pr import PR, PRType
from app.models.user import User
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.schemas.healthkit import (
    HealthKitImportRequest,
    HealthKitImportResponse,
)
from app.schemas.workout import (
    AchievementUnlocked,
    PRAchieved,
    SetResponse,
    WorkoutCreate,
    WorkoutCreateResponse,
    WorkoutExerciseResponse,
    WorkoutResponse,
    WorkoutSummary,
    WorkoutUpdate,
)
from app.services import healthkit_service
from app.services.achievement_service import check_and_unlock_achievements
from app.services.activity_muscles import get_activity_muscles
from app.services.directive_service import check_directive_completion
from app.services.gate_service import check_gate_clear, evaluate_gate_spawns
from app.services.goal_service import update_goal_progress
from app.services.heart_rate_service import ingest_heart_rate
from app.services.hunt_name_service import suggest_hunt_name
from app.services.notification_service import (
    notify_achievement_unlocked,
    notify_gate_opened,
    notify_level_up,
    notify_rank_promotion,
)
from app.services.pr_detection import detect_and_create_prs
from app.services.xp_service import award_xp, calculate_workout_xp, get_or_create_user_progress

logger = logging.getLogger(__name__)

router = APIRouter()


# Energy conversion: HealthKit reports active energy in kilojoules; the UI shows
# kilocalories (1 kcal ≈ 4.184 kJ).
KJ_TO_KCAL = 0.239006


def parse_apple_watch_activity_type(notes: str) -> str | None:
    """Extract the activity type from an Apple-Watch cardio session's notes.

    Cardio sessions imported from HealthKit are saved with notes shaped like
    ``"Tennis - Apple Watch | Distance: 5000m"`` (see
    ``healthkit_service._build_cardio_session``). Returns the activity type
    (``"Tennis"``) or ``None`` when the notes aren't an Apple-Watch activity.
    """
    if not notes or " - Apple Watch" not in notes:
        return None
    activity_type = notes.split(" - Apple Watch", 1)[0].strip()
    return activity_type or None


def _derive_activity_fields(workout: WorkoutSession, total_sets: int) -> dict:
    """Resolve activity fields for a session from either data source.

    WHOOP activities encode type/strain/calories in notes; Apple-Watch cardio
    imports are set-less sessions with ``hr_source="apple_watch"`` and a
    ``"{type} - Apple Watch"`` note (calories derived from kilojoules). A pure
    cardio/sport session is one with no sets but a known activity type.

    Returns a dict with keys ``is_whoop_activity``, ``activity_type``,
    ``strain``, ``calories``, ``is_activity``.
    """
    whoop_data = parse_whoop_notes(workout.notes)
    if whoop_data:
        activity_type = whoop_data.get("activity_type")
        return {
            "is_whoop_activity": whoop_data.get("is_whoop_activity", False),
            "activity_type": activity_type,
            "strain": whoop_data.get("strain"),
            "calories": whoop_data.get("calories"),
            "is_activity": total_sets == 0 and activity_type is not None,
        }

    activity_type = None
    calories = None
    if workout.hr_source == "apple_watch" and total_sets == 0:
        # Prefer the real column (populated since the distance migration);
        # fall back to the legacy notes convention for older rows.
        activity_type = workout.activity_type or parse_apple_watch_activity_type(workout.notes)
        if workout.kilojoules:
            calories = round(workout.kilojoules * KJ_TO_KCAL)
    return {
        "is_whoop_activity": False,
        "activity_type": activity_type,
        "strain": None,
        "calories": calories,
        "is_activity": total_sets == 0 and activity_type is not None,
    }


def _activity_primary_muscles(sorted_exercises: list, activity_type: str | None) -> list | None:
    """Muscle proxy for a cardio/sport activity (Quads/Hamstrings…).

    Prefers the linked Sport/Cardio exercise name, falling back to the parsed
    activity type. Returns ``None`` when no proxy matches so callers keep the
    session's existing muscles.
    """
    proxy_primary, proxy_secondary = [], []
    for we in sorted_exercises:
        if we.exercise:
            primary, secondary = get_activity_muscles(we.exercise.name)
            if primary or secondary:
                proxy_primary, proxy_secondary = primary, secondary
                break
    if not proxy_primary and not proxy_secondary and activity_type:
        proxy_primary, proxy_secondary = get_activity_muscles(activity_type)
    if proxy_primary or proxy_secondary:
        return proxy_primary + [m for m in proxy_secondary if m not in proxy_primary]
    return None


def parse_whoop_notes(notes: str) -> dict:
    """Parse WHOOP activity data from notes field.

    WHOOP activities are saved with notes in this format:
    "{activity_type} - WHOOP Activity | Strain: X | Calories: Y | Time: Z"

    Returns dict with WHOOP fields or None if not a WHOOP activity.
    """
    if not notes or "WHOOP Activity" not in notes:
        return None

    result = {"is_whoop_activity": True}
    parts = notes.split(" | ")

    # First part: "TENNIS - WHOOP Activity"
    if parts and " - WHOOP Activity" in parts[0]:
        result["activity_type"] = parts[0].replace(" - WHOOP Activity", "")

    # Parse remaining parts
    for part in parts[1:]:
        if part.startswith("Strain: "):
            try:
                result["strain"] = float(part.replace("Strain: ", ""))
            except ValueError:
                pass
        elif part.startswith("Calories: "):
            try:
                result["calories"] = int(part.replace("Calories: ", ""))
            except ValueError:
                pass

    return result


@router.post("/debug-error")
async def debug_workout_error(
    workout_data: WorkoutCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Debug endpoint that returns the actual error. Only available in DEBUG mode."""
    from app.core.config import settings
    if not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found"
        )
    import traceback
    try:
        return await _create_workout_impl(workout_data, current_user, db)
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.post("", response_model=WorkoutCreateResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=WorkoutCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_workout(
    workout_data: WorkoutCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return await _create_workout_impl(workout_data, current_user, db)


async def _create_workout_impl(
    workout_data: WorkoutCreate,
    current_user: User,
    db: Session
):
    """
    Create a new workout session with exercises and sets

    Args:
        workout_data: Workout creation data
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Created workout with all exercises and sets

    Raises:
        HTTPException: If exercise IDs are invalid
    """
    # Get user's preferred e1RM formula
    e1rm_formula = get_user_e1rm_formula(db, current_user.id)

    # Idempotency: if the caller sent a client_id we've already saved for
    # this user, return the existing workout instead of creating a duplicate.
    # Protects the iOS offline queue from double-posting after a network blip
    # that actually succeeded server-side. Celebration fields (XP, PRs,
    # achievements) come back empty — the real ones were awarded on the
    # first successful save; re-awarding on retry would inflate counters.
    if workout_data.client_id:
        # Check both active AND soft-deleted workouts for this (user, client_id).
        # A soft-deleted match means the user already created-then-deleted this
        # workout; re-accepting the same client_id would let a client replay
        # the POST and re-award XP/PRs for a workout the user explicitly removed.
        existing = (
            db.query(WorkoutSession)
            .options(
                joinedload(WorkoutSession.workout_exercises)
                .joinedload(WorkoutExercise.sets),
                joinedload(WorkoutSession.workout_exercises)
                .joinedload(WorkoutExercise.exercise),
            )
            .filter(
                WorkoutSession.user_id == current_user.id,
                WorkoutSession.client_id == workout_data.client_id,
            )
            .first()
        )
        if existing:
            if existing.deleted_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Workout with this client_id was deleted. "
                        "Use a new client_id to create a workout."
                    ),
                )
            progress = get_or_create_user_progress(db, current_user.id)
            return WorkoutCreateResponse(
                workout=_build_workout_response(existing),
                xp_earned=0,
                xp_breakdown={},
                total_xp=progress.total_xp,
                level=progress.level,
                leveled_up=False,
                rank=progress.rank,
                rank_changed=False,
                current_streak=progress.current_streak,
                achievements_unlocked=[],
                prs_achieved=[],
            )

    # Create workout session
    workout_session = WorkoutSession(
        user_id=current_user.id,
        client_id=workout_data.client_id,
        date=workout_data.date,
        name=(workout_data.name or "").strip() or None,
        duration_minutes=workout_data.duration_minutes,
        session_rpe=workout_data.session_rpe,
        notes=workout_data.notes,
        # Wearable HR summary (from Apple Watch live session; WHOOP backfills
        # via its own endpoint). Per-set avg/peak are derived from samples below.
        avg_heart_rate=workout_data.avg_heart_rate,
        peak_heart_rate=workout_data.peak_heart_rate,
        strain=workout_data.strain,
        kilojoules=workout_data.kilojoules,
        hr_zone_seconds=workout_data.hr_zone_seconds,
        hr_source=workout_data.hr_source,
    )
    db.add(workout_session)
    db.flush()  # Get workout_session.id

    # Create exercises and sets
    for exercise_data in workout_data.exercises:
        # Verify exercise exists and user has access to it
        exercise = db.query(Exercise).filter(Exercise.id == exercise_data.exercise_id).first()
        if not exercise:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Exercise {exercise_data.exercise_id} not found"
            )

        # Check access for custom exercises
        if exercise.is_custom and exercise.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You don't have access to exercise {exercise.name}"
            )

        # Create workout exercise
        workout_exercise = WorkoutExercise(
            session_id=workout_session.id,
            exercise_id=exercise_data.exercise_id,
            order_index=exercise_data.order_index,
            superset_group_id=exercise_data.superset_group_id
        )
        db.add(workout_exercise)
        db.flush()  # Get workout_exercise.id

        # Create sets
        exercise_sets = []
        for set_data in exercise_data.sets:
            # Calculate e1RM
            if set_data.rpe is not None:
                e1rm = calculate_e1rm_from_rpe(
                    set_data.weight, set_data.reps, set_data.rpe, e1rm_formula
                )
            elif set_data.rir is not None:
                e1rm = calculate_e1rm_from_rir(
                    set_data.weight, set_data.reps, set_data.rir, e1rm_formula
                )
            else:
                e1rm = calculate_e1rm(set_data.weight, set_data.reps, e1rm_formula)

            # Create set
            set_obj = Set(
                workout_exercise_id=workout_exercise.id,
                weight=set_data.weight,
                weight_unit=set_data.weight_unit,
                reps=set_data.reps,
                rpe=set_data.rpe,
                rir=set_data.rir,
                set_number=set_data.set_number,
                e1rm=round(e1rm, 2),
                start_time=set_data.start_time,
                end_time=set_data.end_time,
                avg_heart_rate=set_data.avg_heart_rate,
                peak_heart_rate=set_data.peak_heart_rate,
            )
            db.add(set_obj)
            exercise_sets.append(set_obj)

        # Detect and create PRs for this exercise
        db.flush()  # Ensure sets have IDs
        detect_and_create_prs(db, current_user.id, workout_exercise, exercise_sets)

        # Gate clear-detection (ARISE v2 §6.4) rides the same hook point.
        check_gate_clear(db, current_user.id, workout_exercise, exercise_sets)

        # Update goal progress with best e1RM from this exercise
        if exercise_sets:
            best_set = max(exercise_sets, key=lambda s: s.e1rm or 0)
            if best_set.e1rm and best_set.e1rm > 0:
                update_goal_progress(
                    db=db,
                    user_id=current_user.id,
                    exercise_id=exercise_data.exercise_id,
                    new_e1rm=best_set.e1rm,
                    weight=best_set.weight,
                    reps=best_set.reps,
                    workout_id=workout_session.id
                )

    db.commit()
    db.refresh(workout_session)

    # Calculate and award XP for this workout
    # Get new PRs created for this workout (with exercise details)
    workout_pr_records = db.query(PR).options(
        joinedload(PR.exercise)
    ).filter(
        PR.user_id == current_user.id,
        PR.set_id.in_([s.id for we in workout_session.workout_exercises for s in we.sets])
    ).all()
    workout_prs = len(workout_pr_records)

    # Calculate XP
    xp_result = calculate_workout_xp(db, workout_session, prs_achieved=workout_prs)

    # Award XP and handle level/rank progression
    xp_award = award_xp(
        db,
        current_user.id,
        xp_result["xp_earned"],
        workout_date=workout_session.date
    )

    # Update user progress stats
    progress = get_or_create_user_progress(db, current_user.id)
    progress.total_volume_lb += xp_result["total_volume"]
    progress.total_prs += workout_prs

    # Build context for achievement checking
    all_prs = db.query(PR).options(joinedload(PR.exercise)).filter(PR.user_id == current_user.id).all()
    exercise_prs = {}
    for pr in all_prs:
        exercise_name = pr.exercise.name.lower() if pr.exercise else ""
        # Use e1rm value if weight is None (for E1RM PRs)
        pr_weight = pr.weight if pr.weight is not None else pr.value
        if pr_weight is not None:
            if exercise_name not in exercise_prs or pr_weight > exercise_prs.get(exercise_name, 0):
                exercise_prs[exercise_name] = pr_weight

    achievement_context = {
        "workout_count": progress.total_workouts,
        "level": progress.level,
        "rank": progress.rank,
        "prs_count": progress.total_prs,
        "current_streak": progress.current_streak,
        "exercise_prs": exercise_prs
    }

    # Fetch complete workout with relationships BEFORE any service call that
    # touches relationship collections (achievements, HR ingest).
    # After db.commit() + db.refresh() above, the collections would be empty
    # without this eager-loaded re-query. See CLAUDE.md SQLAlchemy rule.
    workout = db.query(WorkoutSession).options(
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.sets),
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.exercise)
    ).filter(WorkoutSession.id == workout_session.id).first()

    # Ingest raw HR samples (Apple Watch live session): persist them and roll
    # up avg/peak onto sets + session. WHOOP samples arrive later via the
    # WHOOP sync path.
    if workout_data.heart_rate_samples:
        ingest_heart_rate(
            db,
            workout,
            workout_data.heart_rate_samples,
            source=workout_data.hr_source or "apple_watch",
        )

    # Directive completion auto-detect (ARISE v2 §5) — idempotent; mirrors
    # PR detection in running on every ingest path.
    check_directive_completion(db, current_user.id, workout_session.date)

    # Check for newly unlocked achievements AFTER HR ingest + directive
    # completion, so strain-driven (Redline) and directive-streak
    # achievements can unlock on the very workout that earns them.
    newly_unlocked = check_and_unlock_achievements(db, current_user.id, achievement_context)

    db.commit()

    # Gate spawn rules run on workout create, after PR detection (§6.2).
    # evaluate_gate_spawns commits internally.
    newly_spawned_gates = evaluate_gate_spawns(db, current_user.id)

    # ── Send push notifications for triggered events ──
    import asyncio

    for gate in newly_spawned_gates:
        asyncio.ensure_future(notify_gate_opened(db, current_user.id, gate))

    # Notify for each unlocked achievement
    for ach in newly_unlocked:
        asyncio.ensure_future(notify_achievement_unlocked(
            db, current_user.id, ach["name"], ach["description"]
        ))

    # Notify level up
    if xp_award["leveled_up"]:
        asyncio.ensure_future(notify_level_up(
            db, current_user.id, xp_award["new_level"]
        ))

    # Notify rank promotion
    if xp_award["rank_changed"]:
        asyncio.ensure_future(notify_rank_promotion(
            db, current_user.id, xp_award["new_rank"]
        ))

    # Build workout response
    workout_response = _build_workout_response(workout)

    # Build achievements unlocked list
    achievements_unlocked = [
        AchievementUnlocked(
            id=ach["id"],
            name=ach["name"],
            description=ach["description"],
            icon=ach["icon"],
            xp_reward=ach["xp_reward"],
            rarity=ach["rarity"]
        )
        for ach in newly_unlocked
    ]

    # Build PRs achieved list
    prs_achieved_list = []
    for pr in workout_pr_records:
        exercise_name = pr.exercise.name if pr.exercise else "Unknown"
        if pr.pr_type == PRType.E1RM:
            pr_type = "e1rm"
            value = f"{int(pr.value)} lb" if pr.value else "N/A"
        else:
            pr_type = "rep_pr"
            value = f"{int(pr.weight)} lb x {pr.reps}" if pr.weight and pr.reps else "N/A"

        prs_achieved_list.append(PRAchieved(
            exercise_name=exercise_name,
            pr_type=pr_type,
            value=value,
            xp_earned=100  # Fixed XP per PR
        ))

    # Return full response with XP info
    return WorkoutCreateResponse(
        workout=workout_response,
        xp_earned=xp_result["xp_earned"],
        xp_breakdown=xp_result["breakdown"],
        total_xp=xp_award["total_xp"],
        level=xp_award["new_level"],
        leveled_up=xp_award["leveled_up"],
        new_level=xp_award["new_level"] if xp_award["leveled_up"] else None,
        rank=xp_award["new_rank"],
        rank_changed=xp_award["rank_changed"],
        new_rank=xp_award["new_rank"] if xp_award["rank_changed"] else None,
        current_streak=xp_award["current_streak"],
        achievements_unlocked=achievements_unlocked,
        prs_achieved=prs_achieved_list
    )


@router.post("/import-healthkit", response_model=HealthKitImportResponse)
async def import_healthkit(
    payload: HealthKitImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Import a batch of completed Apple-Watch HealthKit workouts.

    Dedups by HealthKit UUID, routes cardio into synthetic sessions and
    strength into existing logged sessions by time-overlap, ingests raw HR
    samples, and idempotently re-credits HR-based quests. ``hr_source`` is
    hard-stamped ``"apple_watch"`` server-side. The service flushes; this
    endpoint owns the final ``db.commit()`` (mirrors the WHOOP sync path).

    Args:
        payload: Batch of HealthKit workouts to import.
        current_user: Currently authenticated user.
        db: Database session.

    Returns:
        HealthKitImportResponse summarizing imported/skipped/created/updated
        sessions, unmatched strength workouts, and completed quests.

    Raises:
        HTTPException: 400 if the import fails.
    """
    try:
        result = healthkit_service.import_healthkit_workouts(
            db, current_user.id, payload.workouts
        )
        db.commit()
        return result
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception(
            "HealthKit import failed for user %s", current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HealthKit import failed",
        )


@router.get("", response_model=List[WorkoutSummary])
@router.get("/", response_model=List[WorkoutSummary])
async def list_workouts(
    limit: int = Query(50, ge=1, le=200, description="Number of workouts to return (max 200)"),
    offset: int = Query(0, ge=0, description="Number of workouts to skip"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List user's workout history with pagination

    Args:
        limit: Maximum number of workouts to return
        offset: Number of workouts to skip
        current_user: Currently authenticated user
        db: Database session

    Returns:
        List of workout summaries ordered by date descending
    """
    # Query workouts with pagination (exclude soft-deleted)
    workouts = db.query(WorkoutSession).options(
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.sets),
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.exercise)
    ).filter(
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.deleted_at == None
    ).order_by(
        WorkoutSession.date.desc()
    ).limit(limit).offset(offset).all()

    # Build summaries
    summaries = []
    for workout in workouts:
        exercise_count = len(workout.workout_exercises)
        total_sets = sum(len(we.sets) for we in workout.workout_exercises)
        # Get exercise names in order
        sorted_exercises = sorted(workout.workout_exercises, key=lambda we: we.order_index)
        exercise_names = [we.exercise.name for we in sorted_exercises if we.exercise]

        # Aggregate primary muscles in exercise order (deduplicated)
        seen_muscles = set()
        primary_muscles = []
        for we in sorted_exercises:
            if we.exercise and we.exercise.primary_muscle:
                m = we.exercise.primary_muscle
                if m not in seen_muscles:
                    seen_muscles.add(m)
                    primary_muscles.append(m)

        # Resolve activity fields (WHOOP notes or Apple-Watch cardio import) and,
        # for activities, surface the muscle proxy (Quads/Hamstrings…) instead of
        # the coarse seeded primary_muscle ("Full Body"/"Legs").
        activity = _derive_activity_fields(workout, total_sets)
        # Suggested name: activity type for pure cardio/sport rows, otherwise
        # the raw strength muscles (before the activity muscle-proxy overwrite)
        # — a WHOOP "WEIGHTLIFTING" tag on a logged session shouldn't beat the
        # muscle split.
        suggested_name = suggest_hunt_name(
            activity["activity_type"] if activity["is_activity"] else None,
            primary_muscles,
        )
        if activity["is_activity"]:
            proxy_muscles = _activity_primary_muscles(sorted_exercises, activity["activity_type"])
            if proxy_muscles:
                primary_muscles = proxy_muscles

        summaries.append(WorkoutSummary(
            id=workout.id,
            user_id=workout.user_id,
            date=to_iso8601_utc(workout.date),
            name=workout.name,
            suggested_name=suggested_name,
            duration_minutes=workout.duration_minutes,
            session_rpe=workout.session_rpe,
            notes=workout.notes,
            exercise_count=exercise_count,
            total_sets=total_sets,
            exercise_names=exercise_names,
            primary_muscles=primary_muscles,
            created_at=to_iso8601_utc(workout.created_at),
            updated_at=to_iso8601_utc(workout.updated_at),
            # Activity fields (WHOOP notes or Apple-Watch cardio import)
            is_whoop_activity=activity["is_whoop_activity"],
            activity_type=activity["activity_type"],
            strain=activity["strain"],
            calories=activity["calories"],
            is_activity=activity["is_activity"],
            exertion_score=compute_exertion_score(workout.hr_zone_seconds),
            # Unified Strain (§7.1): session strain column, else the WHOOP
            # strain parsed from activity notes, else exertion.
            arise_strain=compute_arise_strain(
                workout.strain if workout.strain is not None else activity["strain"],
                workout.hr_zone_seconds,
                workout.hr_source,
            ),
            # Wearable HR provenance (read from session columns; populated by
            # Apple Watch live sessions and the HealthKit/WHOOP import paths).
            avg_heart_rate=workout.avg_heart_rate,
            peak_heart_rate=workout.peak_heart_rate,
            hr_source=workout.hr_source,
            distance_meters=workout.distance_meters,
        ))

    return summaries


@router.get("/{workout_id}", response_model=WorkoutResponse)
async def get_workout(
    workout_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed workout by ID

    Args:
        workout_id: Workout ID
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Complete workout details with exercises and sets

    Raises:
        HTTPException: If workout not found or not accessible
    """
    # Fetch workout with relationships (exclude soft-deleted)
    workout = db.query(WorkoutSession).options(
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.sets),
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.exercise)
    ).filter(
        WorkoutSession.id == workout_id,
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.deleted_at == None
    ).first()

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found"
        )

    return _build_workout_response(workout)


@router.put("/{workout_id}", response_model=WorkoutResponse)
async def update_workout(
    workout_id: str,
    workout_data: WorkoutUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing workout session

    Args:
        workout_id: Workout ID
        workout_data: Updated workout data
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Updated workout details

    Raises:
        HTTPException: If workout not found or not accessible
    """
    # Fetch existing workout (exclude soft-deleted)
    workout = db.query(WorkoutSession).filter(
        WorkoutSession.id == workout_id,
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.deleted_at == None
    ).first()

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found"
        )

    # Update basic fields
    if workout_data.date is not None:
        workout.date = workout_data.date
    # Empty string clears the custom name (display falls back to the
    # suggestion); omitting the field leaves it unchanged.
    if workout_data.name is not None:
        workout.name = workout_data.name.strip() or None
    if workout_data.duration_minutes is not None:
        workout.duration_minutes = workout_data.duration_minutes
    if workout_data.session_rpe is not None:
        workout.session_rpe = workout_data.session_rpe
    if workout_data.notes is not None:
        workout.notes = workout_data.notes

    # If exercises are provided, replace all exercises and sets
    if workout_data.exercises is not None:
        # Get user's preferred e1RM formula
        e1rm_formula = get_user_e1rm_formula(db, current_user.id)

        # Delete existing exercises and sets (cascade will handle sets)
        db.query(WorkoutExercise).filter(
            WorkoutExercise.session_id == workout_id
        ).delete()

        # Create new exercises and sets
        for exercise_data in workout_data.exercises:
            # Verify exercise exists and user has access to it
            exercise = db.query(Exercise).filter(Exercise.id == exercise_data.exercise_id).first()
            if not exercise:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Exercise {exercise_data.exercise_id} not found"
                )

            # Check access for custom exercises
            if exercise.is_custom and exercise.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"You don't have access to exercise {exercise.name}"
                )

            # Create workout exercise
            workout_exercise = WorkoutExercise(
                session_id=workout_id,
                exercise_id=exercise_data.exercise_id,
                order_index=exercise_data.order_index,
                superset_group_id=exercise_data.superset_group_id
            )
            db.add(workout_exercise)
            db.flush()  # Get workout_exercise.id

            # Create sets
            exercise_sets = []
            for set_data in exercise_data.sets:
                # Calculate e1RM
                if set_data.rpe is not None:
                    e1rm = calculate_e1rm_from_rpe(
                        set_data.weight, set_data.reps, set_data.rpe, e1rm_formula
                    )
                elif set_data.rir is not None:
                    e1rm = calculate_e1rm_from_rir(
                        set_data.weight, set_data.reps, set_data.rir, e1rm_formula
                    )
                else:
                    e1rm = calculate_e1rm(set_data.weight, set_data.reps, e1rm_formula)

                # Create set
                set_obj = Set(
                    workout_exercise_id=workout_exercise.id,
                    weight=set_data.weight,
                    weight_unit=set_data.weight_unit,
                    reps=set_data.reps,
                    rpe=set_data.rpe,
                    rir=set_data.rir,
                    set_number=set_data.set_number,
                    e1rm=round(e1rm, 2)
                )
                db.add(set_obj)
                exercise_sets.append(set_obj)

            # Update goal progress with best e1RM from this exercise
            if exercise_sets:
                best_set = max(exercise_sets, key=lambda s: s.e1rm or 0)
                if best_set.e1rm and best_set.e1rm > 0:
                    update_goal_progress(
                        db=db,
                        user_id=current_user.id,
                        exercise_id=exercise_data.exercise_id,
                        new_e1rm=best_set.e1rm,
                        weight=best_set.weight,
                        reps=best_set.reps,
                        workout_id=workout_id
                    )

    db.commit()
    db.refresh(workout)

    # Fetch complete workout with relationships
    updated_workout = db.query(WorkoutSession).options(
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.sets),
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.exercise)
    ).filter(WorkoutSession.id == workout_id).first()

    return _build_workout_response(updated_workout)


@router.delete("/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workout(
    workout_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a workout session (soft delete)

    Args:
        workout_id: Workout ID
        current_user: Currently authenticated user
        db: Database session

    Raises:
        HTTPException: If workout not found or not accessible
    """
    # Fetch existing workout
    workout = db.query(WorkoutSession).filter(
        WorkoutSession.id == workout_id,
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.deleted_at == None  # Only find non-deleted workouts
    ).first()

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found"
        )

    # Soft delete by setting deleted_at timestamp
    workout.deleted_at = datetime.now(timezone.utc)
    db.commit()

    return None


def _build_workout_response(workout: WorkoutSession) -> WorkoutResponse:
    """
    Helper function to build WorkoutResponse from WorkoutSession

    Args:
        workout: WorkoutSession with loaded relationships

    Returns:
        WorkoutResponse
    """
    exercises = []
    for we in workout.workout_exercises:
        sets = [
            SetResponse(
                id=s.id,
                weight=s.weight,
                weight_unit=s.weight_unit.value,
                reps=s.reps,
                rpe=s.rpe,
                rir=s.rir,
                set_number=s.set_number,
                e1rm=s.e1rm,
                start_time=to_iso8601_utc(s.start_time),
                end_time=to_iso8601_utc(s.end_time),
                avg_heart_rate=s.avg_heart_rate,
                peak_heart_rate=s.peak_heart_rate,
                created_at=to_iso8601_utc(s.created_at)
            )
            for s in we.sets
        ]

        exercises.append(WorkoutExerciseResponse(
            id=we.id,
            exercise_id=we.exercise_id,
            exercise_name=we.exercise.name,
            order_index=we.order_index,
            sets=sets,
            superset_group_id=we.superset_group_id,
            created_at=to_iso8601_utc(we.created_at)
        ))

    # Activity classification so the detail screen renders cardio as an activity
    # (type + calories) rather than a 0-set "quest".
    total_sets = sum(len(we.sets) for we in workout.workout_exercises)
    activity = _derive_activity_fields(workout, total_sets)

    # Suggested name mirrors the list endpoint: activity type for pure
    # cardio/sport sessions, muscle split otherwise.
    seen_muscles = set()
    primary_muscles = []
    for we in sorted(workout.workout_exercises, key=lambda we: we.order_index):
        if we.exercise and we.exercise.primary_muscle:
            m = we.exercise.primary_muscle
            if m not in seen_muscles:
                seen_muscles.add(m)
                primary_muscles.append(m)
    suggested_name = suggest_hunt_name(
        activity["activity_type"] if activity["is_activity"] else None,
        primary_muscles,
    )

    return WorkoutResponse(
        id=workout.id,
        user_id=workout.user_id,
        date=to_iso8601_utc(workout.date),
        name=workout.name,
        suggested_name=suggested_name,
        duration_minutes=workout.duration_minutes,
        session_rpe=workout.session_rpe,
        notes=workout.notes,
        exercises=exercises,
        # Wearable session HR summary (Apple Watch / WHOOP / screenshot).
        avg_heart_rate=workout.avg_heart_rate,
        peak_heart_rate=workout.peak_heart_rate,
        strain=workout.strain,
        kilojoules=workout.kilojoules,
        hr_zone_seconds=workout.hr_zone_seconds,
        hr_source=workout.hr_source,
        exertion_score=compute_exertion_score(workout.hr_zone_seconds),
        # Unified Strain (§7.1): session strain column, else the WHOOP strain
        # parsed from activity notes, else exertion.
        arise_strain=compute_arise_strain(
            workout.strain if workout.strain is not None else activity["strain"],
            workout.hr_zone_seconds,
            workout.hr_source,
        ),
        is_activity=activity["is_activity"],
        activity_type=activity["activity_type"],
        calories=activity["calories"],
        distance_meters=workout.distance_meters,
        created_at=to_iso8601_utc(workout.created_at),
        updated_at=to_iso8601_utc(workout.updated_at)
    )
