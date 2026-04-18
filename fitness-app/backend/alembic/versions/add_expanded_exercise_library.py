"""Add expanded exercise library (machines, core, strength variations)

Revision ID: add_expanded_exercises
Revises: f8a2c3d4e5b6
Create Date: 2026-04-18

"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_expanded_exercises'
down_revision = 'f8a2c3d4e5b6'
branch_labels = None
depends_on = None


NEW_EXERCISES = [
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
]


def upgrade():
    conn = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()

    for ex_data in NEW_EXERCISES:
        result = conn.execute(
            text("SELECT id FROM exercises WHERE name = :name"),
            {"name": ex_data["name"]}
        )
        if result.fetchone():
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
                "updated_at": now
            }
        )

        for alias in ex_data.get("aliases", []):
            result = conn.execute(
                text("SELECT id FROM exercises WHERE name = :name"),
                {"name": alias}
            )
            if result.fetchone():
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
                    "updated_at": now
                }
            )


def downgrade():
    conn = op.get_bind()

    all_names = []
    for ex_data in NEW_EXERCISES:
        all_names.append(ex_data["name"])
        all_names.extend(ex_data.get("aliases", []))

    for name in all_names:
        conn.execute(
            text("DELETE FROM exercises WHERE name = :name AND is_custom = false"),
            {"name": name}
        )
