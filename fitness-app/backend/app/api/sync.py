"""
Sync API endpoints for offline data synchronization
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.e1rm import calculate_e1rm, calculate_e1rm_from_rpe, calculate_e1rm_from_rir
from app.models.user import User, UserProfile, E1RMFormula
from app.models.workout import WorkoutSession, WorkoutExercise, Set
from app.models.exercise import Exercise
from app.models.bodyweight import BodyweightEntry
from app.schemas.sync import (
    SyncRequest, SyncResponse, SyncResult, SyncConflict,
    SyncStatusResponse
)
from app.services.pr_detection import detect_and_create_prs

router = APIRouter()


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
    user_profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    e1rm_formula = E1RMFormula.EPLEY
    if user_profile and user_profile.e1rm_formula:
        e1rm_formula = user_profile.e1rm_formula

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
                existing.deleted_at = datetime.utcnow()
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
                duration_minutes=workout_data.duration_minutes,
                session_rpe=workout_data.session_rpe,
                notes=workout_data.notes,
                synced_at=datetime.utcnow()
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
        synced_at=datetime.utcnow().isoformat(),
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
        last_sync_at = last_synced[0].isoformat()

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
