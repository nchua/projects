"""Add one-arm exercise variants

Revision ID: add_one_arm_exercises
Revises: add_dungeon_tables
Create Date: 2026-01-11

"""
from alembic import op
from sqlalchemy import text
import uuid
from datetime import datetime


# revision identifiers, used by Alembic.
revision = 'add_one_arm_exercises'
down_revision = 'add_dungeon_tables'
branch_labels = None
depends_on = None


ONE_ARM_EXERCISES = [
    {
        "name": "One-Arm Preacher Curl",
        "aliases": ["Single Arm Preacher Curl", "1-Arm Preacher Curl"],
        "category": "Pull",
        "primary_muscle": "Biceps",
        "secondary_muscles": []
    },
    {
        "name": "One-Arm Dumbbell Curl",
        "aliases": ["Single Arm Dumbbell Curl", "1-Arm Curl", "Single Arm Curl"],
        "category": "Pull",
        "primary_muscle": "Biceps",
        "secondary_muscles": []
    },
    {
        "name": "One-Arm Hammer Curl",
        "aliases": ["Single Arm Hammer Curl", "1-Arm Hammer Curl"],
        "category": "Pull",
        "primary_muscle": "Biceps",
        "secondary_muscles": ["Forearms"]
    },
    {
        "name": "One-Arm Cable Curl",
        "aliases": ["Single Arm Cable Curl", "1-Arm Cable Curl"],
        "category": "Pull",
        "primary_muscle": "Biceps",
        "secondary_muscles": []
    },
    {
        "name": "One-Arm Lateral Raise",
        "aliases": ["Single Arm Lateral Raise", "1-Arm Lateral Raise"],
        "category": "Push",
        "primary_muscle": "Side Delts",
        "secondary_muscles": []
    },
    {
        "name": "One-Arm Front Raise",
        "aliases": ["Single Arm Front Raise", "1-Arm Front Raise"],
        "category": "Push",
        "primary_muscle": "Front Delts",
        "secondary_muscles": []
    },
    {
        "name": "One-Arm Rear Delt Fly",
        "aliases": ["Single Arm Rear Delt Fly", "1-Arm Reverse Fly"],
        "category": "Push",
        "primary_muscle": "Rear Delts",
        "secondary_muscles": []
    },
    {
        "name": "One-Arm Dumbbell Press",
        "aliases": ["Single Arm Shoulder Press", "1-Arm Dumbbell Press", "Single Arm Dumbbell Press"],
        "category": "Push",
        "primary_muscle": "Shoulders",
        "secondary_muscles": ["Triceps"]
    },
    {
        "name": "One-Arm Tricep Pushdown",
        "aliases": ["Single Arm Tricep Pushdown", "1-Arm Pushdown"],
        "category": "Push",
        "primary_muscle": "Triceps",
        "secondary_muscles": []
    },
    {
        "name": "One-Arm Overhead Extension",
        "aliases": ["Single Arm Overhead Extension", "1-Arm Tricep Extension"],
        "category": "Push",
        "primary_muscle": "Triceps",
        "secondary_muscles": []
    },
]


def upgrade():
    conn = op.get_bind()
    now = datetime.utcnow().isoformat()

    for ex_data in ONE_ARM_EXERCISES:
        # Check if exercise already exists (idempotent)
        result = conn.execute(
            text("SELECT id FROM exercises WHERE name = :name"),
            {"name": ex_data["name"]}
        )
        if result.fetchone():
            print(f"Exercise '{ex_data['name']}' already exists, skipping...")
            continue

        canonical_id = str(uuid.uuid4())
        exercise_id = str(uuid.uuid4())
        secondary_muscles_str = str(ex_data["secondary_muscles"]).replace("'", '"')

        # Insert canonical exercise
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

        # Insert aliases
        for alias in ex_data.get("aliases", []):
            # Check if alias already exists
            result = conn.execute(
                text("SELECT id FROM exercises WHERE name = :name"),
                {"name": alias}
            )
            if result.fetchone():
                print(f"Alias '{alias}' already exists, skipping...")
                continue

            alias_id = str(uuid.uuid4())
            conn.execute(
                text("""
                    INSERT INTO exercises (id, name, canonical_id, category, primary_muscle,
                                           secondary_muscles, is_custom, created_at, updated_at)
                    VALUES (:id, :name, :canonical_id, :category, :primary_muscle,
                            :secondary_muscles, false, :created_at, :updated_at)
                """),
                {
                    "id": alias_id,
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

    # Remove all one-arm exercises and their aliases
    all_names = []
    for ex_data in ONE_ARM_EXERCISES:
        all_names.append(ex_data["name"])
        all_names.extend(ex_data.get("aliases", []))

    for name in all_names:
        conn.execute(
            text("DELETE FROM exercises WHERE name = :name AND is_custom = false"),
            {"name": name}
        )
