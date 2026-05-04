"""
Seed exercise library with 50+ common exercises
"""
import uuid

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.exercise import Exercise

exercises_data = [
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
    {"name": "Seated Dumbbell Press", "aliases": ["Seated DB Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": ["Triceps"]},
    {"name": "Seated Shoulder Press", "aliases": ["Seated OHP", "Seated Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": ["Triceps"]},
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
    {"name": "Romanian Deadlift", "aliases": ["RDL"], "category": "Pull", "primary_muscle": "Hamstrings", "secondary_muscles": ["Back", "Glutes"]},
    {"name": "Stiff-Leg Deadlift", "aliases": ["Stiff Leg Deadlift", "SLDL"], "category": "Pull", "primary_muscle": "Hamstrings", "secondary_muscles": ["Back", "Glutes"]},
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

    # Machine Exercises
    {"name": "Machine Chest Press", "aliases": ["Chest Press Machine", "Seated Chest Press"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": ["Triceps", "Front Delts"]},
    {"name": "Pec Deck", "aliases": ["Machine Fly", "Pec Deck Machine", "Machine Flye"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": []},
    {"name": "Machine Shoulder Press", "aliases": ["Shoulder Press Machine", "Seated Machine Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": ["Triceps"]},
    {"name": "Smith Machine Bench Press", "aliases": ["Smith Bench", "Smith Bench Press"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": ["Triceps", "Front Delts"]},
    {"name": "Smith Machine Squat", "aliases": ["Smith Squat"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes", "Hamstrings"]},
    {"name": "Cable Crossover", "aliases": ["Cable Crossovers", "Cable Cross"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": []},
    {"name": "Machine Row", "aliases": ["Seated Machine Row", "Machine Back Row"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Biceps"]},
    {"name": "Chest Supported Row", "aliases": ["Chest Supported DB Row", "Incline Row"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Biceps"]},
    {"name": "Reverse Pec Deck", "aliases": ["Reverse Machine Fly", "Machine Reverse Fly"], "category": "Pull", "primary_muscle": "Rear Delts", "secondary_muscles": ["Upper Back"]},
    {"name": "Cable Lateral Raise", "aliases": ["Cable Side Raise", "Cable Lat Raise"], "category": "Push", "primary_muscle": "Side Delts", "secondary_muscles": []},
    {"name": "Machine Hip Abductor", "aliases": ["Hip Abductor", "Abductor Machine"], "category": "Legs", "primary_muscle": "Glutes", "secondary_muscles": []},
    {"name": "Machine Hip Adductor", "aliases": ["Hip Adductor", "Adductor Machine"], "category": "Legs", "primary_muscle": "Adductors", "secondary_muscles": []},

    # Additional Core Exercises
    {"name": "Medicine Ball Rotations", "aliases": ["Med Ball Rotations", "Medicine Ball Twist"], "category": "Core", "primary_muscle": "Obliques", "secondary_muscles": ["Abs"]},
    {"name": "Bicycle Crunches", "aliases": ["Bicycle Crunch"], "category": "Core", "primary_muscle": "Abs", "secondary_muscles": ["Obliques"]},
    {"name": "Dead Bug", "aliases": ["Dead Bugs"], "category": "Core", "primary_muscle": "Core", "secondary_muscles": ["Lower Abs"]},
    {"name": "Mountain Climbers", "aliases": ["Mountain Climber"], "category": "Core", "primary_muscle": "Core", "secondary_muscles": ["Shoulders", "Quads"]},
    {"name": "Pallof Press", "aliases": ["Pallof Press Hold", "Anti-Rotation Press"], "category": "Core", "primary_muscle": "Core", "secondary_muscles": ["Obliques"]},
    {"name": "Decline Sit-ups", "aliases": ["Decline Sit-up", "Decline Situps"], "category": "Core", "primary_muscle": "Abs", "secondary_muscles": []},
    {"name": "V-ups", "aliases": ["V-up", "V Ups"], "category": "Core", "primary_muscle": "Abs", "secondary_muscles": ["Lower Abs"]},
    {"name": "Woodchoppers", "aliases": ["Cable Woodchop", "Wood Chop"], "category": "Core", "primary_muscle": "Obliques", "secondary_muscles": ["Core"]},

    # Additional Strength Variations
    {"name": "Skull Crushers", "aliases": ["Lying Tricep Extension", "EZ Bar Skull Crusher"], "category": "Push", "primary_muscle": "Triceps", "secondary_muscles": []},
    {"name": "EZ Bar Curl", "aliases": ["EZ Curl", "EZ Barbell Curl"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": []},
    {"name": "Concentration Curl", "aliases": ["Concentration Curls", "Seated Concentration Curl"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": []},
    {"name": "Incline Dumbbell Curl", "aliases": ["Incline DB Curl", "Incline Curl"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": []},
    {"name": "Spider Curl", "aliases": ["Spider Curls"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": []},
    {"name": "Tricep Kickbacks", "aliases": ["Kickbacks", "DB Kickbacks", "Dumbbell Kickback"], "category": "Push", "primary_muscle": "Triceps", "secondary_muscles": []},
    {"name": "Trap Bar Deadlift", "aliases": ["Hex Bar Deadlift", "Trap Bar DL"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Glutes", "Hamstrings", "Quads"]},
    {"name": "Good Mornings", "aliases": ["Good Morning", "Barbell Good Morning"], "category": "Pull", "primary_muscle": "Hamstrings", "secondary_muscles": ["Back", "Glutes"]},
    {"name": "Step-ups", "aliases": ["Step Up", "Dumbbell Step-up", "Barbell Step-up"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes"]},
    {"name": "Rack Pull", "aliases": ["Rack Pulls", "Block Pull"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Glutes", "Traps"]},

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
    print("   Categories: Push, Pull, Legs, Core, Accessories")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_exercises(db)
    finally:
        db.close()
