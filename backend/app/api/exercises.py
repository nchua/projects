"""
Exercise API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional, List
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.exercise import Exercise
from app.schemas.exercise import ExerciseCreate, ExerciseResponse

router = APIRouter()


@router.get("", response_model=List[ExerciseResponse])
@router.get("/", response_model=List[ExerciseResponse])
async def list_exercises(
    category: Optional[str] = Query(None, description="Filter by category (Push, Pull, Legs, Core, Accessories)"),
    search: Optional[str] = Query(None, description="Search by exercise name"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all exercises (seeded + user's custom exercises)

    Args:
        category: Optional category filter
        search: Optional name search
        current_user: Currently authenticated user
        db: Database session

    Returns:
        List of exercises matching filters
    """
    # Base query: seeded exercises (is_custom=False) OR user's custom exercises
    query = db.query(Exercise).filter(
        or_(
            Exercise.is_custom == False,
            Exercise.user_id == current_user.id
        )
    )

    # Apply category filter
    if category:
        query = query.filter(Exercise.category == category)

    # Apply search filter (case-insensitive partial match)
    if search:
        query = query.filter(Exercise.name.ilike(f"%{search}%"))

    # Order by name
    exercises = query.order_by(Exercise.name).all()

    # Convert to response format
    return [
        ExerciseResponse(
            id=ex.id,
            name=ex.name,
            canonical_id=ex.canonical_id,
            category=ex.category,
            primary_muscle=ex.primary_muscle,
            secondary_muscles=ex.secondary_muscles,
            is_custom=ex.is_custom,
            user_id=ex.user_id,
            created_at=ex.created_at.isoformat(),
            updated_at=ex.updated_at.isoformat()
        )
        for ex in exercises
    ]


@router.post("", response_model=ExerciseResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ExerciseResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_exercise(
    exercise_data: ExerciseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a custom exercise for the current user

    Args:
        exercise_data: Exercise creation data
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Created exercise information

    Raises:
        HTTPException: If exercise name already exists for this user
    """
    # Check if custom exercise with this name already exists for this user
    existing = db.query(Exercise).filter(
        Exercise.name.ilike(exercise_data.name),
        Exercise.user_id == current_user.id,
        Exercise.is_custom == True
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Custom exercise '{exercise_data.name}' already exists"
        )

    # Create new custom exercise
    new_exercise = Exercise(
        name=exercise_data.name,
        category=exercise_data.category,
        primary_muscle=exercise_data.primary_muscle,
        secondary_muscles=exercise_data.secondary_muscles,
        is_custom=True,
        user_id=current_user.id
    )

    db.add(new_exercise)
    db.commit()
    db.refresh(new_exercise)

    return ExerciseResponse(
        id=new_exercise.id,
        name=new_exercise.name,
        canonical_id=new_exercise.canonical_id,
        category=new_exercise.category,
        primary_muscle=new_exercise.primary_muscle,
        secondary_muscles=new_exercise.secondary_muscles,
        is_custom=new_exercise.is_custom,
        user_id=new_exercise.user_id,
        created_at=new_exercise.created_at.isoformat(),
        updated_at=new_exercise.updated_at.isoformat()
    )


@router.get("/{exercise_id}", response_model=ExerciseResponse)
async def get_exercise(
    exercise_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get details for a specific exercise

    Args:
        exercise_id: Exercise ID
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Exercise details

    Raises:
        HTTPException: If exercise not found or not accessible
    """
    exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()

    if not exercise:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exercise not found"
        )

    # Check if user has access (seeded exercise OR user's custom exercise)
    if exercise.is_custom and exercise.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this exercise"
        )

    return ExerciseResponse(
        id=exercise.id,
        name=exercise.name,
        canonical_id=exercise.canonical_id,
        category=exercise.category,
        primary_muscle=exercise.primary_muscle,
        secondary_muscles=exercise.secondary_muscles,
        is_custom=exercise.is_custom,
        user_id=exercise.user_id,
        created_at=exercise.created_at.isoformat(),
        updated_at=exercise.updated_at.isoformat()
    )
