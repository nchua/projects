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

# Abbreviation dictionary for search expansion
ABBREVIATIONS = {
    "bb": "barbell",
    "db": "dumbbell",
    "ohp": "overhead press",
    "rdl": "romanian deadlift",
    "dl": "deadlift",
    "bp": "bench press",
    "incl": "incline",
    "decl": "decline",
    "lat": "lateral",
    "ext": "extension",
    "tri": "tricep",
    "bi": "bicep",
    "sl": "single leg",
    "cg": "close grip",
    "1-arm": "one-arm",
    "1 arm": "one arm",
}


def expand_search_query(search: str) -> List[str]:
    """
    Expand abbreviations in search query.

    Examples:
        'bb curl' -> ['bb curl', 'barbell curl']
        'ohp' -> ['ohp', 'overhead press']
        'db lat raise' -> ['db lat raise', 'dumbbell lateral raise']
    """
    terms = [search]
    words = search.lower().split()

    # Expand each word if it's an abbreviation
    expanded_words = [ABBREVIATIONS.get(w, w) for w in words]
    expanded = " ".join(expanded_words)

    if expanded != search.lower():
        terms.append(expanded)

    return terms

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
    {"name": "Lateral Raises", "aliases": ["Side Raises", "DB Lateral Raises", "Lateral Shoulder Raise", "Lateral Raise", "Side Raise"], "category": "Push", "primary_muscle": "Side Delts", "secondary_muscles": []},
    {"name": "Front Raises", "aliases": ["Front Delt Raises", "Front Raise", "Front Delt Raise"], "category": "Push", "primary_muscle": "Front Delts", "secondary_muscles": []},
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
    {"name": "Face Pulls", "aliases": ["Cable Face Pulls", "Face Pull", "Cable Face Pull"], "category": "Pull", "primary_muscle": "Rear Delts", "secondary_muscles": ["Upper Back"]},
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

    # One-Arm Exercise Variants (separate PRs from 2-arm versions)
    {"name": "One-Arm Preacher Curl", "aliases": ["Single Arm Preacher Curl", "1-Arm Preacher Curl"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": []},
    {"name": "One-Arm Dumbbell Curl", "aliases": ["Single Arm Dumbbell Curl", "1-Arm Curl", "Single Arm Curl"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": []},
    {"name": "One-Arm Hammer Curl", "aliases": ["Single Arm Hammer Curl", "1-Arm Hammer Curl"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": ["Forearms"]},
    {"name": "One-Arm Cable Curl", "aliases": ["Single Arm Cable Curl", "1-Arm Cable Curl"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": []},
    {"name": "One-Arm Lateral Raise", "aliases": ["Single Arm Lateral Raise", "1-Arm Lateral Raise"], "category": "Push", "primary_muscle": "Side Delts", "secondary_muscles": []},
    {"name": "One-Arm Front Raise", "aliases": ["Single Arm Front Raise", "1-Arm Front Raise"], "category": "Push", "primary_muscle": "Front Delts", "secondary_muscles": []},
    {"name": "One-Arm Rear Delt Fly", "aliases": ["Single Arm Rear Delt Fly", "1-Arm Reverse Fly"], "category": "Push", "primary_muscle": "Rear Delts", "secondary_muscles": []},
    {"name": "One-Arm Dumbbell Press", "aliases": ["Single Arm Shoulder Press", "1-Arm Dumbbell Press", "Single Arm Dumbbell Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": ["Triceps"]},
    {"name": "One-Arm Tricep Pushdown", "aliases": ["Single Arm Tricep Pushdown", "1-Arm Pushdown"], "category": "Push", "primary_muscle": "Triceps", "secondary_muscles": []},
    {"name": "One-Arm Overhead Extension", "aliases": ["Single Arm Overhead Extension", "1-Arm Tricep Extension"], "category": "Push", "primary_muscle": "Triceps", "secondary_muscles": []},

    # Sports & Cardio
    {"name": "Tennis", "aliases": ["Tennis Match", "Tennis Practice"], "category": "Sport", "primary_muscle": "Full Body", "secondary_muscles": []},
    {"name": "Pickleball", "aliases": ["Pickleball Match", "Pickleball Game"], "category": "Sport", "primary_muscle": "Full Body", "secondary_muscles": []},
    {"name": "Padel", "aliases": ["Padel Match", "Padel Tennis"], "category": "Sport", "primary_muscle": "Full Body", "secondary_muscles": []},
    {"name": "Running", "aliases": ["Run", "Jog", "Jogging"], "category": "Cardio", "primary_muscle": "Legs", "secondary_muscles": []},
    {"name": "Cycling", "aliases": ["Biking", "Bike Ride", "Spinning"], "category": "Cardio", "primary_muscle": "Legs", "secondary_muscles": []},
    {"name": "Swimming", "aliases": ["Swim", "Lap Swimming"], "category": "Cardio", "primary_muscle": "Full Body", "secondary_muscles": []},
    {"name": "Rowing", "aliases": ["Row Machine", "Rowing Machine", "Erg"], "category": "Cardio", "primary_muscle": "Full Body", "secondary_muscles": ["Back", "Legs"]},
    {"name": "Jump Rope", "aliases": ["Skipping", "Skip Rope"], "category": "Cardio", "primary_muscle": "Calves", "secondary_muscles": []},
    {"name": "Stair Climber", "aliases": ["StairMaster", "Stair Machine"], "category": "Cardio", "primary_muscle": "Legs", "secondary_muscles": []},
    {"name": "Elliptical", "aliases": ["Elliptical Machine", "Cross Trainer"], "category": "Cardio", "primary_muscle": "Full Body", "secondary_muscles": []},
    {"name": "Walking", "aliases": ["Walk", "Treadmill Walk"], "category": "Cardio", "primary_muscle": "Legs", "secondary_muscles": []},
    {"name": "HIIT", "aliases": ["High Intensity Interval Training", "Interval Training"], "category": "Cardio", "primary_muscle": "Full Body", "secondary_muscles": []},
    {"name": "Basketball", "aliases": ["Basketball Game", "Hoops"], "category": "Sport", "primary_muscle": "Full Body", "secondary_muscles": []},
    {"name": "Soccer", "aliases": ["Football", "Soccer Match"], "category": "Sport", "primary_muscle": "Legs", "secondary_muscles": []},
    {"name": "Golf", "aliases": ["Golf Round", "Golfing"], "category": "Sport", "primary_muscle": "Core", "secondary_muscles": ["Back"]},
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

    # Apply search filter (case-insensitive partial match with abbreviation expansion)
    if search:
        search_terms = expand_search_query(search)
        search_filters = [Exercise.name.ilike(f"%{term}%") for term in search_terms]
        query = query.filter(or_(*search_filters))

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


@router.post("/test-create-workout", status_code=status.HTTP_200_OK)
async def test_create_workout(db: Session = Depends(get_db)):
    """Debug endpoint to test workout creation with full error logging"""
    from app.models.workout import WorkoutSession, WorkoutExercise, Set
    from app.models.exercise import Exercise
    from app.services.pr_detection import detect_and_create_prs
    from app.services.xp_service import calculate_workout_xp, award_xp, get_or_create_user_progress
    from app.services.achievement_service import check_and_unlock_achievements
    from app.services.quest_service import update_quest_progress
    from app.models.pr import PR
    from datetime import datetime
    import traceback

    result = {"steps": []}

    try:
        # Find user
        from app.models.user import User
        user = db.query(User).first()
        if not user:
            return {"error": "No user found"}
        result["steps"].append(f"Found user: {user.email}")

        # Find exercise
        exercise = db.query(Exercise).filter(Exercise.name == "Squat").first()
        if not exercise:
            return {"error": "Squat exercise not found"}
        result["steps"].append(f"Found exercise: {exercise.name} ({exercise.id})")

        # Create workout
        workout = WorkoutSession(
            user_id=user.id,
            date=datetime.utcnow(),
            duration_minutes=60
        )
        db.add(workout)
        db.flush()
        result["steps"].append(f"Created workout: {workout.id}")

        # Create exercise entry
        workout_ex = WorkoutExercise(
            session_id=workout.id,
            exercise_id=exercise.id,
            order_index=0
        )
        db.add(workout_ex)
        db.flush()
        result["steps"].append(f"Created workout exercise: {workout_ex.id}")

        # Create set
        set_obj = Set(
            workout_exercise_id=workout_ex.id,
            weight=225,
            reps=5,
            set_number=1,
            e1rm=250.0
        )
        db.add(set_obj)
        db.flush()
        result["steps"].append(f"Created set: {set_obj.id}")

        # Try PR detection
        try:
            prs = detect_and_create_prs(db, user.id, workout_ex, [set_obj])
            result["steps"].append(f"PR detection done: {len(prs)} PRs")
        except Exception as e:
            result["steps"].append(f"PR detection error: {str(e)}")
            result["pr_traceback"] = traceback.format_exc()

        db.commit()
        result["steps"].append("Committed to DB")

        # Try XP calculation
        try:
            workout_prs = db.query(PR).filter(
                PR.user_id == user.id,
                PR.set_id.in_([set_obj.id])
            ).count()
            result["steps"].append(f"PR count: {workout_prs}")
        except Exception as e:
            result["steps"].append(f"PR count error: {str(e)}")
            result["pr_count_traceback"] = traceback.format_exc()

        try:
            xp_result = calculate_workout_xp(db, workout, prs_achieved=0)
            result["steps"].append(f"XP calculation done: {xp_result}")
        except Exception as e:
            result["steps"].append(f"XP error: {str(e)}")
            result["xp_traceback"] = traceback.format_exc()

        try:
            xp_award = award_xp(db, user.id, 50, workout_date=workout.date)
            result["steps"].append(f"XP awarded: {xp_award}")
        except Exception as e:
            result["steps"].append(f"Award XP error: {str(e)}")
            result["award_xp_traceback"] = traceback.format_exc()

        try:
            progress = get_or_create_user_progress(db, user.id)
            result["steps"].append(f"Got progress: level {progress.level}")
        except Exception as e:
            result["steps"].append(f"Progress error: {str(e)}")
            result["progress_traceback"] = traceback.format_exc()

        try:
            completed_quests = update_quest_progress(db, user.id, workout)
            result["steps"].append(f"Quest progress: {completed_quests}")
        except Exception as e:
            result["steps"].append(f"Quest error: {str(e)}")
            result["quest_traceback"] = traceback.format_exc()

        db.commit()
        result["success"] = True
        return result

    except Exception as e:
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
        return result


@router.post("/migrate-db", status_code=status.HTTP_200_OK)
async def migrate_database(db: Session = Depends(get_db)):
    """
    Run database migrations to add missing columns.
    This is a temporary endpoint for fixing production database schema.
    """
    from sqlalchemy import text
    migrations = []

    # Check if set_id column exists in prs table
    try:
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='prs' AND column_name='set_id'"))
        exists = result.fetchone() is not None
        if exists:
            migrations.append("set_id column already exists in prs table")
        else:
            db.execute(text("ALTER TABLE prs ADD COLUMN set_id VARCHAR"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_prs_set_id ON prs(set_id)"))
            db.commit()
            migrations.append("Added set_id column to prs table")
    except Exception as e:
        db.rollback()
        migrations.append(f"Error: {str(e)}")

    return {"migrations": migrations}
