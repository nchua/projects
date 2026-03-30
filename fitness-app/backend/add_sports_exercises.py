"""
Add sports and cardio exercises to existing database
"""
import uuid

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.exercise import Exercise

sports_data = [
    # Sports & Cardio
    {
        "name": "Tennis",
        "aliases": ["Tennis Match", "Tennis Practice"],
        "category": "Sport",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Pickleball",
        "aliases": ["Pickleball Match", "Pickleball Game"],
        "category": "Sport",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Padel",
        "aliases": ["Padel Match", "Padel Tennis"],
        "category": "Sport",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Running",
        "aliases": ["Run", "Jog", "Jogging"],
        "category": "Cardio",
        "primary_muscle": "Legs",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Cycling",
        "aliases": ["Biking", "Bike Ride", "Spinning"],
        "category": "Cardio",
        "primary_muscle": "Legs",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Swimming",
        "aliases": ["Swim", "Lap Swimming"],
        "category": "Cardio",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Rowing",
        "aliases": ["Row Machine", "Rowing Machine", "Erg"],
        "category": "Cardio",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Back", "Legs"],
    },
    {
        "name": "Jump Rope",
        "aliases": ["Skipping", "Skip Rope"],
        "category": "Cardio",
        "primary_muscle": "Calves",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Stair Climber",
        "aliases": ["StairMaster", "Stair Machine"],
        "category": "Cardio",
        "primary_muscle": "Legs",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Elliptical",
        "aliases": ["Elliptical Machine", "Cross Trainer"],
        "category": "Cardio",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Walking",
        "aliases": ["Walk", "Treadmill Walk"],
        "category": "Cardio",
        "primary_muscle": "Legs",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "HIIT",
        "aliases": [
            "High Intensity Interval Training",
            "Interval Training",
        ],
        "category": "Cardio",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Basketball",
        "aliases": ["Basketball Game", "Hoops"],
        "category": "Sport",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Soccer",
        "aliases": ["Football", "Soccer Match"],
        "category": "Sport",
        "primary_muscle": "Legs",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Golf",
        "aliases": ["Golf Round", "Golfing"],
        "category": "Sport",
        "primary_muscle": "Core",
        "secondary_muscles": ["Back"],
    },
]


def add_sports_exercises(db: Session):
    """Add sports and cardio exercises to the database"""
    print("Adding sports and cardio exercises...\n")

    exercises_created = 0
    exercises_skipped = 0

    for ex_data in sports_data:
        existing = (
            db.query(Exercise)
            .filter(Exercise.name == ex_data["name"])
            .first()
        )
        if existing:
            print(f"  Skipped: {ex_data['name']} already exists")
            exercises_skipped += 1
            continue

        canonical_id = str(uuid.uuid4())
        exercise = Exercise(
            id=str(uuid.uuid4()),
            name=ex_data["name"],
            canonical_id=canonical_id,
            category=ex_data["category"],
            primary_muscle=ex_data["primary_muscle"],
            secondary_muscles=ex_data["secondary_muscles"],
            is_custom=False,
            user_id=None,
        )
        db.add(exercise)
        exercises_created += 1
        print(f"  Added {ex_data['name']}")

        for alias in ex_data.get("aliases", []):
            alias_existing = (
                db.query(Exercise)
                .filter(Exercise.name == alias)
                .first()
            )
            if alias_existing:
                continue

            alias_exercise = Exercise(
                id=str(uuid.uuid4()),
                name=alias,
                canonical_id=canonical_id,
                category=ex_data["category"],
                primary_muscle=ex_data["primary_muscle"],
                secondary_muscles=ex_data["secondary_muscles"],
                is_custom=False,
                user_id=None,
            )
            db.add(alias_exercise)
            exercises_created += 1

    db.commit()
    print(f"\nAdded {exercises_created} exercise entries")
    print(f"Skipped {exercises_skipped} existing exercises")
    print("New categories: Sport, Cardio")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        add_sports_exercises(db)
    finally:
        db.close()
