"""
Sync API endpoints for offline data synchronization
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.e1rm import (
    calculate_e1rm,
    calculate_e1rm_from_rir,
    calculate_e1rm_from_rpe,
    get_user_e1rm_formula,
)
from app.core.utils import derive_local_date, to_iso8601_utc
from app.models.bodyweight import BodyweightEntry
from app.models.exercise import Exercise
from app.models.pr import PR
from app.models.user import User, UserProfile
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.schemas.sync import (
    SyncConflict,
    SyncRequest,
    SyncResponse,
    SyncResult,
    SyncStatusResponse,
)
from app.services.achievement_service import check_and_unlock_achievements
from app.services.directive_service import check_directive_completion
from app.services.gate_service import check_gate_clear
from app.services.pr_detection import detect_and_create_prs
from app.services.xp_service import award_xp, calculate_workout_xp, get_or_create_user_progress

router = APIRouter()


def _award_workout_xp(db: Session, user: User, workout_session: WorkoutSession) -> None:
    """
    Award XP for a newly synced workout, mirroring the POST /workouts pipeline.

    Counts the workout's PRs, awards XP, updates progress totals
    (volume, PR count), and re-checks achievements. The caller must only
    invoke this for brand-new workouts — retries of an already-synced
    date must stay XP-neutral.

    Args:
        db: Database session
        user: Owner of the workout
        workout_session: Flushed (but not yet committed) workout session
    """
    workout_prs = db.query(PR).filter(
        PR.user_id == user.id,
        PR.set_id.in_([
            s.id
            for we in workout_session.workout_exercises
            for s in we.sets
        ])
    ).count()

    # Eager re-load so calculate_workout_xp can walk exercises/sets
    # (relationship collections are unreliable right after flushes —
    # see CLAUDE.md SQLAlchemy joinedload rule).
    loaded_workout = db.query(WorkoutSession).options(
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.sets),
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.exercise)
    ).filter(WorkoutSession.id == workout_session.id).first()

    xp_result = calculate_workout_xp(db, loaded_workout, prs_achieved=workout_prs)
    award_xp(
        db,
        user.id,
        xp_result["xp_earned"],
        workout_date=workout_session.date
    )

    progress = get_or_create_user_progress(db, user.id)
    progress.total_volume_lb += xp_result["total_volume"]
    progress.total_prs += workout_prs

    # Build the per-exercise PR map the same way POST /workouts does
    # so exercise-milestone achievements can unlock via sync.
    all_prs = db.query(PR).options(joinedload(PR.exercise)).filter(
        PR.user_id == user.id
    ).all()
    exercise_prs: dict[str, float] = {}
    for pr in all_prs:
        exercise_name = pr.exercise.name.lower() if pr.exercise else ""
        pr_weight = pr.weight if pr.weight is not None else pr.value
        if pr_weight is not None and pr_weight > exercise_prs.get(exercise_name, 0):
            exercise_prs[exercise_name] = pr_weight

    check_and_unlock_achievements(db, user.id, {
        "workout_count": progress.total_workouts,
        "level": progress.level,
        "rank": progress.rank,
        "prs_count": progress.total_prs,
        "current_streak": progress.current_streak,
        "exercise_prs": exercise_prs,
    })


@router.post("", response_model=SyncResponse)
@router.post("/", response_model=SyncResponse)
async def sync_data(
    sync_data: SyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Bulk sync endpoint for offline changes

    Implements last-write-wins with device priority conflict resolution.

    Args:
        sync_data: Data to sync (workouts, bodyweight, profile)
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Sync results including any conflicts
    """
    results = []
    conflicts = []
    workouts_synced = 0
    bodyweight_synced = 0
    profile_synced = False

    # Get user's preferred e1RM formula
    e1rm_formula = get_user_e1rm_formula(db, current_user.id)

    # Sync workouts
    for workout_data in sync_data.workouts:
        try:
            # Check if workout already exists (by date and notes as identifier)
            existing = db.query(WorkoutSession).filter(
                WorkoutSession.user_id == current_user.id,
                WorkoutSession.date == workout_data.date,
                WorkoutSession.deleted_at == None
            ).first()

            if existing:
                # Conflict - client wins (device priority)
                # Delete existing and create new
                existing.deleted_at = datetime.now(timezone.utc)
                conflicts.append(SyncConflict(
                    entity_type="workout",
                    entity_id=existing.id,
                    resolution="client_wins",
                    details=f"Replaced workout from {workout_data.date}"
                ))

            # Create new workout
            workout_session = WorkoutSession(
                user_id=current_user.id,
                date=workout_data.date,
                local_date=workout_data.local_date or derive_local_date(workout_data.date),
                duration_minutes=workout_data.duration_minutes,
                session_rpe=workout_data.session_rpe,
                notes=workout_data.notes,
                synced_at=datetime.now(timezone.utc)
            )
            db.add(workout_session)
            db.flush()

            # Create exercises and sets
            for exercise_data in workout_data.exercises:
                exercise = db.query(Exercise).filter(Exercise.id == exercise_data.exercise_id).first()
                if not exercise:
                    continue

                workout_exercise = WorkoutExercise(
                    session_id=workout_session.id,
                    exercise_id=exercise_data.exercise_id,
                    order_index=exercise_data.order_index
                )
                db.add(workout_exercise)
                db.flush()

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

                # Detect PRs
                db.flush()
                detect_and_create_prs(db, current_user.id, workout_exercise, exercise_sets)

                # Gate clear-detection (ARISE v2 §6.4) rides the same hook.
                check_gate_clear(db, current_user.id, workout_exercise, exercise_sets)

            # Award XP for the synced workout, mirroring the POST /workouts
            # pipeline (offline-logged workouts previously earned nothing).
            # Skipped on the conflict path: the replaced same-date workout
            # already earned its XP, so a retry/re-send of the same batch
            # must stay XP-neutral (POST /workouts gets this from client_id
            # dedupe; sync has no client_id, so the conflict flag is the guard).
            if existing is None:
                _award_workout_xp(db, current_user, workout_session)

            # Directive completion auto-detect (ARISE v2 §5) — idempotent,
            # so safe to run on the conflict path too.
            check_directive_completion(db, current_user.id, workout_session.date)

            results.append(SyncResult(
                entity_type="workout",
                entity_id=workout_session.id,
                status="created"
            ))
            workouts_synced += 1

        except Exception as e:
            results.append(SyncResult(
                entity_type="workout",
                entity_id="unknown",
                status=f"error: {str(e)}"
            ))

    # Sync bodyweight entries
    for bw_data in sync_data.bodyweight_entries:
        try:
            # Convert to lb if needed
            weight_lb = bw_data.weight
            if bw_data.weight_unit.value == "kg":
                weight_lb = bw_data.weight * 2.20462

            # Check if entry exists for this date
            existing = db.query(BodyweightEntry).filter(
                BodyweightEntry.user_id == current_user.id,
                BodyweightEntry.date == bw_data.date
            ).first()

            if existing:
                # Update existing (client wins)
                existing.weight_lb = weight_lb
                existing.source = bw_data.source
                results.append(SyncResult(
                    entity_type="bodyweight",
                    entity_id=existing.id,
                    status="updated"
                ))
            else:
                # Create new
                entry = BodyweightEntry(
                    user_id=current_user.id,
                    date=bw_data.date,
                    weight_lb=weight_lb,
                    source=bw_data.source or "sync"
                )
                db.add(entry)
                db.flush()
                results.append(SyncResult(
                    entity_type="bodyweight",
                    entity_id=entry.id,
                    status="created"
                ))

            bodyweight_synced += 1

        except Exception as e:
            results.append(SyncResult(
                entity_type="bodyweight",
                entity_id="unknown",
                status=f"error: {str(e)}"
            ))

    # Sync profile
    if sync_data.profile:
        try:
            profile = db.query(UserProfile).filter(
                UserProfile.user_id == current_user.id
            ).first()

            if not profile:
                profile = UserProfile(user_id=current_user.id)
                db.add(profile)

            # Update fields if provided
            if sync_data.profile.age is not None:
                profile.age = sync_data.profile.age
            if sync_data.profile.bodyweight is not None:
                profile.bodyweight_lb = sync_data.profile.bodyweight
            if sync_data.profile.height_inches is not None:
                profile.height_inches = sync_data.profile.height_inches

            results.append(SyncResult(
                entity_type="profile",
                entity_id=current_user.id,
                status="updated"
            ))
            profile_synced = True

        except Exception as e:
            results.append(SyncResult(
                entity_type="profile",
                entity_id="unknown",
                status=f"error: {str(e)}"
            ))

    db.commit()

    return SyncResponse(
        success=True,
        synced_at=to_iso8601_utc(datetime.now(timezone.utc)),
        results=results,
        conflicts=conflicts,
        workouts_synced=workouts_synced,
        bodyweight_entries_synced=bodyweight_synced,
        profile_synced=profile_synced
    )


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get last sync status and timestamp

    Args:
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Sync status including last sync time and pending changes
    """
    # Get last synced workout
    last_synced = db.query(WorkoutSession.synced_at).filter(
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.synced_at != None
    ).order_by(WorkoutSession.synced_at.desc()).first()

    last_sync_at = None
    if last_synced and last_synced[0]:
        last_sync_at = to_iso8601_utc(last_synced[0])

    # Count pending (unsynced) workouts
    pending_workouts = db.query(WorkoutSession).filter(
        WorkoutSession.user_id == current_user.id,
        WorkoutSession.synced_at == None,
        WorkoutSession.deleted_at == None
    ).count()

    # For now, we don't track sync status on bodyweight entries
    # This would need a synced_at column on BodyweightEntry
    pending_bodyweight = 0

    return SyncStatusResponse(
        last_sync_at=last_sync_at,
        pending_workouts=pending_workouts,
        pending_bodyweight_entries=pending_bodyweight,
        is_synced=(pending_workouts == 0 and pending_bodyweight == 0)
    )
