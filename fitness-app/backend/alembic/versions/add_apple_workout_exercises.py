"""Add Apple Watch activity exercises (Yoga, Pilates, Strength Training, etc.)

Seeds the activities that Apple Watch/Fitness logs but weren't previously in
our exercise library, so screenshot processing can link them via
match_activity_to_exercise. Also merges the two pre-existing heads
(f8a2c3d4e5b6 and b2c3d4e5f6g7) into a single lineage.

Revision ID: add_apple_workout_exercises
Revises: f8a2c3d4e5b6, b2c3d4e5f6g7
Create Date: 2026-04-19

"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_apple_workout_exercises'
down_revision = ('f8a2c3d4e5b6', 'b2c3d4e5f6g7')
branch_labels = None
depends_on = None


APPLE_WORKOUT_EXERCISES = [
    # Flexibility / Mind-Body
    {
        "name": "Yoga",
        "aliases": ["Yoga Session", "Vinyasa", "Hatha Yoga"],
        "category": "Flexibility",
        "primary_muscle": "Full Body",
        "secondary_muscles": [],
    },
    {
        "name": "Pilates",
        "aliases": ["Pilates Session", "Mat Pilates", "Reformer Pilates"],
        "category": "Flexibility",
        "primary_muscle": "Core",
        "secondary_muscles": ["Full Body"],
    },
    {
        "name": "Core Training",
        "aliases": ["Core Workout", "Ab Workout"],
        "category": "Flexibility",
        "primary_muscle": "Core",
        "secondary_muscles": [],
    },
    # Generic strength (Apple Watch "Strength Training" / "Functional Strength")
    {
        "name": "Strength Training",
        "aliases": ["Traditional Strength Training", "Weight Training", "Lifting"],
        "category": "Strength",
        "primary_muscle": "Full Body",
        "secondary_muscles": [],
    },
    {
        "name": "Functional Strength Training",
        "aliases": ["Functional Training"],
        "category": "Strength",
        "primary_muscle": "Full Body",
        "secondary_muscles": [],
    },
    # Cardio
    {
        "name": "Hiking",
        "aliases": ["Hike", "Trail Hike"],
        "category": "Cardio",
        "primary_muscle": "Legs",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Dance",
        "aliases": ["Dance Workout", "Dancing", "Zumba"],
        "category": "Cardio",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
    # Combat sports
    {
        "name": "Boxing",
        "aliases": ["Boxing Workout", "Heavy Bag"],
        "category": "Sport",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Kickboxing",
        "aliases": ["Kickboxing Workout", "Muay Thai"],
        "category": "Sport",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Martial Arts",
        "aliases": ["Karate", "Taekwondo", "Judo", "BJJ", "Jiu-Jitsu"],
        "category": "Sport",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
    # Outdoor / action sports
    {
        "name": "Climbing",
        "aliases": ["Bouldering", "Rock Climbing", "Indoor Climbing"],
        "category": "Sport",
        "primary_muscle": "Back",
        "secondary_muscles": ["Arms", "Full Body"],
    },
    {
        "name": "Skiing",
        "aliases": ["Downhill Skiing", "Cross Country Skiing", "Ski"],
        "category": "Sport",
        "primary_muscle": "Legs",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Snowboarding",
        "aliases": ["Snowboard"],
        "category": "Sport",
        "primary_muscle": "Legs",
        "secondary_muscles": ["Core"],
    },
    {
        "name": "Surfing",
        "aliases": ["Surf", "Paddleboard", "Stand Up Paddleboarding"],
        "category": "Sport",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
    {
        "name": "Volleyball",
        "aliases": ["Beach Volleyball", "Volleyball Match"],
        "category": "Sport",
        "primary_muscle": "Full Body",
        "secondary_muscles": ["Cardio"],
    },
]


def upgrade():
    conn = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()

    for ex_data in APPLE_WORKOUT_EXERCISES:
        result = conn.execute(
            text("SELECT id FROM exercises WHERE name = :name"),
            {"name": ex_data["name"]},
        )
        if result.fetchone():
            print(f"Exercise '{ex_data['name']}' already exists, skipping...")
            continue

        canonical_id = str(uuid.uuid4())
        exercise_id = str(uuid.uuid4())
        secondary_muscles_str = str(ex_data["secondary_muscles"]).replace("'", '"')

        conn.execute(
            text("""
                INSERT INTO exercises (id, name, canonical_id, category, primary_muscle,
                                       secondary_muscles, is_custom, created_at, updated_at)
                VALUES (:id, :name, :canonical_id, :category, :primary_muscle,
                        :secondary_muscles, false, :created_at, :updated_at)
            """),
            {
                "id": exercise_id,
                "name": ex_data["name"],
                "canonical_id": canonical_id,
                "category": ex_data["category"],
                "primary_muscle": ex_data["primary_muscle"],
                "secondary_muscles": secondary_muscles_str,
                "created_at": now,
                "updated_at": now,
            },
        )

        for alias in ex_data.get("aliases", []):
            result = conn.execute(
                text("SELECT id FROM exercises WHERE name = :name"),
                {"name": alias},
            )
            if result.fetchone():
                print(f"Alias '{alias}' already exists, skipping...")
                continue

            conn.execute(
                text("""
                    INSERT INTO exercises (id, name, canonical_id, category, primary_muscle,
                                           secondary_muscles, is_custom, created_at, updated_at)
                    VALUES (:id, :name, :canonical_id, :category, :primary_muscle,
                            :secondary_muscles, false, :created_at, :updated_at)
                """),
                {
                    "id": str(uuid.uuid4()),
                    "name": alias,
                    "canonical_id": canonical_id,
                    "category": ex_data["category"],
                    "primary_muscle": ex_data["primary_muscle"],
                    "secondary_muscles": secondary_muscles_str,
                    "created_at": now,
                    "updated_at": now,
                },
            )


def downgrade():
    conn = op.get_bind()

    all_names = []
    for ex_data in APPLE_WORKOUT_EXERCISES:
        all_names.append(ex_data["name"])
        all_names.extend(ex_data.get("aliases", []))

    if all_names:
        conn.execute(
            text("DELETE FROM exercises WHERE name = ANY(:names)"),
            {"names": all_names},
        )
