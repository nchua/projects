"""
Exercise API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional, List
import uuid
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.exercise import Exercise
from app.schemas.exercise import ExerciseCreate, ExerciseResponse

router = APIRouter()

# Exercise seed data
EXERCISES_DATA = [
    # Push Exercises
    {"name": "Barbell Bench Press", "aliases": ["Bench Press", "BB Bench"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": ["Triceps", "Front Delts"]},
    {"name": "Incline Barbell Bench Press", "aliases": ["Incline Bench", "Incline BB Bench", "Incline Bench Press"], "category": "Push", "primary_muscle": "Upper Chest", "secondary_muscles": ["Triceps", "Front Delts"]},
    {"name": "Decline Barbell Bench Press", "aliases": ["Decline Bench"], "category": "Push", "primary_muscle": "Lower Chest", "secondary_muscles": ["Triceps"]},
    {"name": "Dumbbell Bench Press", "aliases": ["DB Bench", "Dumbbell Bench"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": ["Triceps", "Front Delts"]},
    {"name": "Incline Dumbbell Bench Press", "aliases": ["Incline DB Bench"], "category": "Push", "primary_muscle": "Upper Chest", "secondary_muscles": ["Triceps", "Front Delts"]},
    {"name": "Dumbbell Flyes", "aliases": ["DB Flyes", "Chest Flyes"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": []},
    {"name": "Cable Flyes", "aliases": ["Cable Chest Flyes"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": []},
    {"name": "Push-ups", "aliases": ["Pushups", "Press-ups"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": ["Triceps", "Front Delts"]},
    {"name": "Overhead Press", "aliases": ["OHP", "Military Press", "Shoulder Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": ["Triceps", "Upper Chest"]},
    {"name": "Seated Dumbbell Press", "aliases": ["Seated DB Press", "Seated Shoulder Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": ["Triceps"]},
    {"name": "Arnold Press", "aliases": ["Arnold Shoulder Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": []},
    {"name": "Lateral Raises", "aliases": ["Side Raises", "DB Lateral Raises", "Lateral Shoulder Raise"], "category": "Push", "primary_muscle": "Side Delts", "secondary_muscles": []},
    {"name": "Front Raises", "aliases": ["Front Delt Raises"], "category": "Push", "primary_muscle": "Front Delts", "secondary_muscles": []},
    {"name": "Rear Delt Flyes", "aliases": ["Reverse Flyes", "Rear Delts"], "category": "Push", "primary_muscle": "Rear Delts", "secondary_muscles": []},
    {"name": "Close-Grip Bench Press", "aliases": ["CG Bench", "Close Grip Bench"], "category": "Push", "primary_muscle": "Triceps", "secondary_muscles": ["Chest"]},
    {"name": "Tricep Dips", "aliases": ["Dips", "Triceps Dips", "Chest Dip"], "category": "Push", "primary_muscle": "Triceps", "secondary_muscles": ["Chest"]},
    {"name": "Tricep Pushdowns", "aliases": ["Cable Pushdowns", "Triceps Pushdowns", "Triceps Pulldown"], "category": "Push", "primary_muscle": "Triceps", "secondary_muscles": []},
    {"name": "Overhead Tricep Extension", "aliases": ["Tricep Extensions"], "category": "Push", "primary_muscle": "Triceps", "secondary_muscles": []},

    # Pull Exercises
    {"name": "Barbell Deadlift", "aliases": ["Deadlift", "Conventional Deadlift"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Glutes", "Hamstrings", "Traps"]},
    {"name": "Sumo Deadlift", "aliases": ["Sumo DL"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Glutes", "Hamstrings", "Quads"]},
    {"name": "Romanian Deadlift", "aliases": ["RDL", "Stiff-Leg Deadlift"], "category": "Pull", "primary_muscle": "Hamstrings", "secondary_muscles": ["Back", "Glutes"]},
    {"name": "Single Leg Romanian Deadlift", "aliases": ["Single Leg RDL", "SL RDL", "One Leg RDL"], "category": "Pull", "primary_muscle": "Hamstrings", "secondary_muscles": ["Glutes", "Core"]},
    {"name": "Pull-ups", "aliases": ["Pullups", "Chin-ups", "Pull-Up"], "category": "Pull", "primary_muscle": "Lats", "secondary_muscles": ["Biceps"]},
    {"name": "Lat Pulldown", "aliases": ["Lat Pulldowns", "Lat Pull Down", "Lat Pull Downs"], "category": "Pull", "primary_muscle": "Lats", "secondary_muscles": ["Biceps"]},
    {"name": "Straight Arm Pulldown", "aliases": ["Straight Arm Pull Down", "Straight Arm Lat Pulldown"], "category": "Pull", "primary_muscle": "Lats", "secondary_muscles": []},
    {"name": "Dumbbell High Pull", "aliases": ["High Pull", "DB High Pull"], "category": "Pull", "primary_muscle": "Traps", "secondary_muscles": ["Shoulders", "Upper Back"]},
    {"name": "Barbell Row", "aliases": ["BB Row", "Bent-Over Row", "Bent Over Row"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Biceps"]},
    {"name": "Dumbbell Row", "aliases": ["DB Row", "One-Arm Row"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Biceps"]},
    {"name": "T-Bar Row", "aliases": ["T Bar Row"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Biceps"]},
    {"name": "Seated Cable Row", "aliases": ["Cable Row", "Seated Row"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Biceps"]},
    {"name": "Face Pulls", "aliases": ["Cable Face Pulls"], "category": "Pull", "primary_muscle": "Rear Delts", "secondary_muscles": ["Upper Back"]},
    {"name": "Barbell Curl", "aliases": ["BB Curl", "Bicep Curl"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": []},
    {"name": "Dumbbell Curl", "aliases": ["DB Curl"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": []},
    {"name": "Hammer Curl", "aliases": ["Hammer Curls"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": ["Forearms"]},
    {"name": "Preacher Curl", "aliases": ["Preacher Curls"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": []},
    {"name": "Cable Curl", "aliases": ["Cable Bicep Curl"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": []},

    # Legs Exercises
    {"name": "Barbell Back Squat", "aliases": ["Squat", "Back Squat", "BB Squat"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes", "Hamstrings"]},
    {"name": "Front Squat", "aliases": ["Front Squats"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes"]},
    {"name": "Goblet Squat", "aliases": ["Goblet Squats"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes"]},
    {"name": "Bulgarian Split Squat", "aliases": ["Split Squat", "Bulgarian Squat"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes"]},
    {"name": "Leg Press", "aliases": ["Leg Press Machine"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes"]},
    {"name": "Hack Squat", "aliases": ["Hack Squat Machine"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": []},
    {"name": "Leg Extension", "aliases": ["Leg Extensions"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": []},
    {"name": "Leg Curl", "aliases": ["Leg Curls", "Hamstring Curl"], "category": "Legs", "primary_muscle": "Hamstrings", "secondary_muscles": []},
    {"name": "Walking Lunges", "aliases": ["Lunges", "Alternating Lunge"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes"]},
    {"name": "Hip Thrust", "aliases": ["Barbell Hip Thrust", "Glute Bridge"], "category": "Legs", "primary_muscle": "Glutes", "secondary_muscles": ["Hamstrings"]},
    {"name": "Standing Calf Raise", "aliases": ["Calf Raises", "Calf Raise"], "category": "Legs", "primary_muscle": "Calves", "secondary_muscles": []},
    {"name": "Seated Calf Raise", "aliases": ["Seated Calf Raises"], "category": "Legs", "primary_muscle": "Calves", "secondary_muscles": []},

    # Core Exercises
    {"name": "Plank", "aliases": ["Front Plank"], "category": "Core", "primary_muscle": "Core", "secondary_muscles": []},
    {"name": "Side Plank", "aliases": ["Side Planks"], "category": "Core", "primary_muscle": "Obliques", "secondary_muscles": ["Core"]},
    {"name": "Crunches", "aliases": ["Crunch"], "category": "Core", "primary_muscle": "Abs", "secondary_muscles": []},
    {"name": "Russian Twists", "aliases": ["Russian Twist"], "category": "Core", "primary_muscle": "Obliques", "secondary_muscles": ["Abs"]},
    {"name": "Hanging Leg Raise", "aliases": ["Leg Raises", "Hanging Leg Raises"], "category": "Core", "primary_muscle": "Lower Abs", "secondary_muscles": []},
    {"name": "Ab Wheel Rollout", "aliases": ["Ab Wheel", "Rollouts"], "category": "Core", "primary_muscle": "Core", "secondary_muscles": []},
    {"name": "Cable Crunches", "aliases": ["Cable Crunch"], "category": "Core", "primary_muscle": "Abs", "secondary_muscles": []},

    # Accessories
    {"name": "Shrugs", "aliases": ["Barbell Shrugs", "Dumbbell Shrugs"], "category": "Accessories", "primary_muscle": "Traps", "secondary_muscles": []},
    {"name": "Farmer's Walk", "aliases": ["Farmers Walk", "Farmer Carry"], "category": "Accessories", "primary_muscle": "Forearms", "secondary_muscles": ["Traps", "Core"]},
    {"name": "Wrist Curls", "aliases": ["Wrist Curl"], "category": "Accessories", "primary_muscle": "Forearms", "secondary_muscles": []},
]


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


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_exercises(
    db: Session = Depends(get_db)
):
    """
    Seed the exercise library with common exercises.
    This is idempotent - it won't create duplicates if exercises already exist.

    Returns:
        Summary of seeded exercises
    """
    # Check if exercises already exist
    existing_count = db.query(Exercise).filter(Exercise.is_custom == False).count()
    if existing_count > 0:
        return {"message": f"Exercises already seeded ({existing_count} exist)", "exercises_created": 0}

    exercises_created = 0
    for ex_data in EXERCISES_DATA:
        # Create canonical exercise
        canonical_id = str(uuid.uuid4())
        exercise = Exercise(
            id=str(uuid.uuid4()),
            name=ex_data["name"],
            canonical_id=canonical_id,
            category=ex_data["category"],
            primary_muscle=ex_data["primary_muscle"],
            secondary_muscles=ex_data["secondary_muscles"],
            is_custom=False,
            user_id=None
        )
        db.add(exercise)
        exercises_created += 1

        # Create alias exercises
        for alias in ex_data.get("aliases", []):
            alias_exercise = Exercise(
                id=str(uuid.uuid4()),
                name=alias,
                canonical_id=canonical_id,
                category=ex_data["category"],
                primary_muscle=ex_data["primary_muscle"],
                secondary_muscles=ex_data["secondary_muscles"],
                is_custom=False,
                user_id=None
            )
            db.add(alias_exercise)
            exercises_created += 1

    db.commit()
    return {
        "message": f"Seeded {exercises_created} exercise entries ({len(EXERCISES_DATA)} unique exercises with aliases)",
        "exercises_created": exercises_created
    }
