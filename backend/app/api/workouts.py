"""
Workout API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.e1rm import calculate_e1rm, calculate_e1rm_from_rpe, calculate_e1rm_from_rir
from app.models.user import User, E1RMFormula
from app.models.workout import WorkoutSession, WorkoutExercise, Set
from app.models.exercise import Exercise
from app.schemas.workout import (
    WorkoutCreate, WorkoutResponse, WorkoutSummary,
    WorkoutExerciseResponse, SetResponse
)

router = APIRouter()


@router.post("", response_model=WorkoutResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=WorkoutResponse, status_code=status.HTTP_201_CREATED)
async def create_workout(
    workout_data: WorkoutCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
    from app.models.user import UserProfile
    user_profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    e1rm_formula = E1RMFormula.EPLEY  # Default
    if user_profile and user_profile.e1rm_formula:
        e1rm_formula = user_profile.e1rm_formula

    # Create workout session
    workout_session = WorkoutSession(
        user_id=current_user.id,
        date=workout_data.date,
        duration_minutes=workout_data.duration_minutes,
        session_rpe=workout_data.session_rpe,
        notes=workout_data.notes
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
            order_index=exercise_data.order_index
        )
        db.add(workout_exercise)
        db.flush()  # Get workout_exercise.id

        # Create sets
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

    db.commit()
    db.refresh(workout_session)

    # Fetch complete workout with relationships
    workout = db.query(WorkoutSession).options(
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.sets),
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.exercise)
    ).filter(WorkoutSession.id == workout_session.id).first()

    # Build response
    return _build_workout_response(workout)


@router.get("", response_model=List[WorkoutSummary])
@router.get("/", response_model=List[WorkoutSummary])
async def list_workouts(
    limit: int = Query(20, ge=1, le=100, description="Number of workouts to return"),
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
    # Query workouts with pagination
    workouts = db.query(WorkoutSession).options(
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.sets)
    ).filter(
        WorkoutSession.user_id == current_user.id
    ).order_by(
        WorkoutSession.date.desc()
    ).limit(limit).offset(offset).all()

    # Build summaries
    summaries = []
    for workout in workouts:
        exercise_count = len(workout.workout_exercises)
        total_sets = sum(len(we.sets) for we in workout.workout_exercises)

        summaries.append(WorkoutSummary(
            id=workout.id,
            user_id=workout.user_id,
            date=workout.date.isoformat(),
            duration_minutes=workout.duration_minutes,
            session_rpe=workout.session_rpe,
            notes=workout.notes,
            exercise_count=exercise_count,
            total_sets=total_sets,
            created_at=workout.created_at.isoformat(),
            updated_at=workout.updated_at.isoformat()
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
    # Fetch workout with relationships
    workout = db.query(WorkoutSession).options(
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.sets),
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.exercise)
    ).filter(
        WorkoutSession.id == workout_id,
        WorkoutSession.user_id == current_user.id
    ).first()

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found"
        )

    return _build_workout_response(workout)


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
                created_at=s.created_at.isoformat()
            )
            for s in we.sets
        ]

        exercises.append(WorkoutExerciseResponse(
            id=we.id,
            exercise_id=we.exercise_id,
            exercise_name=we.exercise.name,
            order_index=we.order_index,
            sets=sets,
            created_at=we.created_at.isoformat()
        ))

    return WorkoutResponse(
        id=workout.id,
        user_id=workout.user_id,
        date=workout.date.isoformat(),
        duration_minutes=workout.duration_minutes,
        session_rpe=workout.session_rpe,
        notes=workout.notes,
        exercises=exercises,
        created_at=workout.created_at.isoformat(),
        updated_at=workout.updated_at.isoformat()
    )
