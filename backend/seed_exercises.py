"""
Seed exercise library with 50+ common exercises
"""
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.exercise import Exercise
import uuid

exercises_data = [
    # Push Exercises
    {"name": "Barbell Bench Press", "aliases": ["Bench Press", "BB Bench"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": ["Triceps", "Front Delts"]},
    {"name": "Incline Barbell Bench Press", "aliases": ["Incline Bench", "Incline BB Bench"], "category": "Push", "primary_muscle": "Upper Chest", "secondary_muscles": ["Triceps", "Front Delts"]},
    {"name": "Decline Barbell Bench Press", "aliases": ["Decline Bench"], "category": "Push", "primary_muscle": "Lower Chest", "secondary_muscles": ["Triceps"]},
    {"name": "Dumbbell Bench Press", "aliases": ["DB Bench", "Dumbbell Bench"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": ["Triceps", "Front Delts"]},
    {"name": "Incline Dumbbell Bench Press", "aliases": ["Incline DB Bench"], "category": "Push", "primary_muscle": "Upper Chest", "secondary_muscles": ["Triceps", "Front Delts"]},
    {"name": "Dumbbell Flyes", "aliases": ["DB Flyes", "Chest Flyes"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": []},
    {"name": "Cable Flyes", "aliases": ["Cable Chest Flyes"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": []},
    {"name": "Push-ups", "aliases": ["Pushups", "Press-ups"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": ["Triceps", "Front Delts"]},
    {"name": "Overhead Press", "aliases": ["OHP", "Military Press", "Shoulder Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": ["Triceps", "Upper Chest"]},
    {"name": "Seated Dumbbell Press", "aliases": ["Seated DB Press", "Seated Shoulder Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": ["Triceps"]},
    {"name": "Arnold Press", "aliases": ["Arnold Shoulder Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": []},
    {"name": "Lateral Raises", "aliases": ["Side Raises", "DB Lateral Raises"], "category": "Push", "primary_muscle": "Side Delts", "secondary_muscles": []},
    {"name": "Front Raises", "aliases": ["Front Delt Raises"], "category": "Push", "primary_muscle": "Front Delts", "secondary_muscles": []},
    {"name": "Rear Delt Flyes", "aliases": ["Reverse Flyes", "Rear Delts"], "category": "Push", "primary_muscle": "Rear Delts", "secondary_muscles": []},
    {"name": "Close-Grip Bench Press", "aliases": ["CG Bench", "Close Grip Bench"], "category": "Push", "primary_muscle": "Triceps", "secondary_muscles": ["Chest"]},
    {"name": "Tricep Dips", "aliases": ["Dips", "Triceps Dips"], "category": "Push", "primary_muscle": "Triceps", "secondary_muscles": ["Chest"]},
    {"name": "Tricep Pushdowns", "aliases": ["Cable Pushdowns", "Triceps Pushdowns"], "category": "Push", "primary_muscle": "Triceps", "secondary_muscles": []},
    {"name": "Overhead Tricep Extension", "aliases": ["Tricep Extensions"], "category": "Push", "primary_muscle": "Triceps", "secondary_muscles": []},

    # Pull Exercises
    {"name": "Barbell Deadlift", "aliases": ["Deadlift", "Conventional Deadlift"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Glutes", "Hamstrings", "Traps"]},
    {"name": "Sumo Deadlift", "aliases": ["Sumo DL"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Glutes", "Hamstrings", "Quads"]},
    {"name": "Romanian Deadlift", "aliases": ["RDL", "Stiff-Leg Deadlift"], "category": "Pull", "primary_muscle": "Hamstrings", "secondary_muscles": ["Back", "Glutes"]},
    {"name": "Single Leg Romanian Deadlift", "aliases": ["Single Leg RDL", "SL RDL", "One Leg RDL"], "category": "Pull", "primary_muscle": "Hamstrings", "secondary_muscles": ["Glutes", "Core"]},
    {"name": "Pull-ups", "aliases": ["Pullups", "Chin-ups"], "category": "Pull", "primary_muscle": "Lats", "secondary_muscles": ["Biceps"]},
    {"name": "Lat Pulldown", "aliases": ["Lat Pulldowns", "Lat Pull Down", "Lat Pull Downs"], "category": "Pull", "primary_muscle": "Lats", "secondary_muscles": ["Biceps"]},
    {"name": "Straight Arm Pulldown", "aliases": ["Straight Arm Pull Down", "Straight Arm Lat Pulldown"], "category": "Pull", "primary_muscle": "Lats", "secondary_muscles": []},
    {"name": "Dumbbell High Pull", "aliases": ["High Pull", "DB High Pull"], "category": "Pull", "primary_muscle": "Traps", "secondary_muscles": ["Shoulders", "Upper Back"]},
    {"name": "Barbell Row", "aliases": ["BB Row", "Bent-Over Row"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Biceps"]},
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
    {"name": "Walking Lunges", "aliases": ["Lunges"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes"]},
    {"name": "Hip Thrust", "aliases": ["Barbell Hip Thrust", "Glute Bridge"], "category": "Legs", "primary_muscle": "Glutes", "secondary_muscles": ["Hamstrings"]},
    {"name": "Standing Calf Raise", "aliases": ["Calf Raises"], "category": "Legs", "primary_muscle": "Calves", "secondary_muscles": []},
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

    # Sports & Cardio
    {"name": "Tennis", "aliases": ["Tennis Match", "Tennis Practice"], "category": "Sport", "primary_muscle": "Full Body", "secondary_muscles": ["Cardio"]},
    {"name": "Pickleball", "aliases": ["Pickleball Match", "Pickleball Game"], "category": "Sport", "primary_muscle": "Full Body", "secondary_muscles": ["Cardio"]},
    {"name": "Padel", "aliases": ["Padel Match", "Padel Tennis"], "category": "Sport", "primary_muscle": "Full Body", "secondary_muscles": ["Cardio"]},
    {"name": "Running", "aliases": ["Run", "Jog", "Jogging"], "category": "Cardio", "primary_muscle": "Legs", "secondary_muscles": ["Cardio"]},
    {"name": "Cycling", "aliases": ["Biking", "Bike Ride", "Spinning"], "category": "Cardio", "primary_muscle": "Legs", "secondary_muscles": ["Cardio"]},
    {"name": "Swimming", "aliases": ["Swim", "Lap Swimming"], "category": "Cardio", "primary_muscle": "Full Body", "secondary_muscles": ["Cardio"]},
    {"name": "Rowing", "aliases": ["Row Machine", "Rowing Machine", "Erg"], "category": "Cardio", "primary_muscle": "Full Body", "secondary_muscles": ["Back", "Legs"]},
    {"name": "Jump Rope", "aliases": ["Skipping", "Skip Rope"], "category": "Cardio", "primary_muscle": "Calves", "secondary_muscles": ["Cardio"]},
    {"name": "Stair Climber", "aliases": ["StairMaster", "Stair Machine"], "category": "Cardio", "primary_muscle": "Legs", "secondary_muscles": ["Cardio"]},
    {"name": "Elliptical", "aliases": ["Elliptical Machine", "Cross Trainer"], "category": "Cardio", "primary_muscle": "Full Body", "secondary_muscles": ["Cardio"]},
    {"name": "Walking", "aliases": ["Walk", "Treadmill Walk"], "category": "Cardio", "primary_muscle": "Legs", "secondary_muscles": ["Cardio"]},
    {"name": "HIIT", "aliases": ["High Intensity Interval Training", "Interval Training"], "category": "Cardio", "primary_muscle": "Full Body", "secondary_muscles": ["Cardio"]},
    {"name": "Basketball", "aliases": ["Basketball Game", "Hoops"], "category": "Sport", "primary_muscle": "Full Body", "secondary_muscles": ["Cardio"]},
    {"name": "Soccer", "aliases": ["Football", "Soccer Match"], "category": "Sport", "primary_muscle": "Legs", "secondary_muscles": ["Cardio"]},
    {"name": "Golf", "aliases": ["Golf Round", "Golfing"], "category": "Sport", "primary_muscle": "Core", "secondary_muscles": ["Back"]},
]


def seed_exercises(db: Session):
    """Seed the exercise library"""
    print("🏋️  Seeding exercise library...\n")

    # Check if exercises already exist
    existing_count = db.query(Exercise).count()
    if existing_count > 0:
        print(f"⚠️  Database already has {existing_count} exercises. Skipping seed.")
        return

    exercises_created = 0
    for ex_data in exercises_data:
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
                canonical_id=canonical_id,  # Link to canonical exercise
                category=ex_data["category"],
                primary_muscle=ex_data["primary_muscle"],
                secondary_muscles=ex_data["secondary_muscles"],
                is_custom=False,
                user_id=None
            )
            db.add(alias_exercise)
            exercises_created += 1

    db.commit()
    print(f"✅ Created {exercises_created} exercise entries ({len(exercises_data)} unique exercises with aliases)")
    print(f"   Categories: Push, Pull, Legs, Core, Accessories")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_exercises(db)
    finally:
        db.close()
