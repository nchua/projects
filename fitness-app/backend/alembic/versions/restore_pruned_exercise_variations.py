"""Restore exercise variations removed by an over-aggressive cleanup pass

The previous cleanup correctly merged pure abbreviations/plurals (e.g.
"Romanian Deadlift" vs "Romanian Deadlifts", "BB X" vs "Barbell X") into
aliases. It also removed genuinely *distinct* movements, leaving big gaps:
hamstrings had been pruned down to essentially just the leg curl, and the
seated shoulder press had no barbell/smith/landmine variations.

This migration idempotently restores those movements as their own canonical
exercises (each tracks its own PR), mirroring the additions in
``seed_exercises.py``. The first three entries are canonicals that already
ship in the seed but may have been deleted from existing/production databases
by the cleanup, so we re-add them if absent.

Revision ID: restore_pruned_exercises
Revises: add_healthkit_uuid
Create Date: 2026-06-21

"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = 'restore_pruned_exercises'
down_revision = 'add_healthkit_uuid'
branch_labels = None
depends_on = None


# Core hamstring/hinge canonicals that should already exist but may have been
# pruned from production (re-added only if missing) ...
RESTORED_EXERCISES = [
    {"name": "Romanian Deadlift", "aliases": ["RDL", "Stiff-Leg Deadlift"], "category": "Pull", "primary_muscle": "Hamstrings", "secondary_muscles": ["Back", "Glutes"]},
    {"name": "Leg Curl", "aliases": ["Leg Curls", "Hamstring Curl"], "category": "Legs", "primary_muscle": "Hamstrings", "secondary_muscles": []},
    {"name": "Good Mornings", "aliases": ["Good Morning", "Barbell Good Morning"], "category": "Pull", "primary_muscle": "Hamstrings", "secondary_muscles": ["Back", "Glutes"]},
    # ... and the newly-added distinct variations.
    {"name": "Seated Barbell Shoulder Press", "aliases": ["Seated Barbell Press", "Seated Military Press", "Seated BB Shoulder Press", "Seated Overhead Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": ["Triceps", "Upper Chest"]},
    {"name": "Smith Machine Shoulder Press", "aliases": ["Smith Shoulder Press", "Smith Machine Overhead Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": ["Triceps"]},
    {"name": "Push Press", "aliases": ["Barbell Push Press", "Overhead Push Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": ["Triceps", "Legs"]},
    {"name": "Landmine Press", "aliases": ["Landmine Shoulder Press", "Half-Kneeling Landmine Press"], "category": "Push", "primary_muscle": "Shoulders", "secondary_muscles": ["Triceps", "Upper Chest"]},
    {"name": "Box Squat", "aliases": ["Box Squats", "Barbell Box Squat"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes", "Hamstrings"]},
    {"name": "Safety Bar Squat", "aliases": ["SSB Squat", "Safety Squat Bar Squat", "Safety Bar Squats"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes", "Hamstrings"]},
    {"name": "Pause Squat", "aliases": ["Paused Squat", "Tempo Squat"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes", "Hamstrings"]},
    {"name": "Sissy Squat", "aliases": ["Sissy Squats"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": []},
    {"name": "Belt Squat", "aliases": ["Belt Squats", "Belt Squat Machine"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes"]},
    {"name": "Deficit Deadlift", "aliases": ["Deficit DL", "Deficit Deadlifts"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Glutes", "Hamstrings", "Traps"]},
    {"name": "Reverse Lunge", "aliases": ["Reverse Lunges", "Barbell Reverse Lunge", "Dumbbell Reverse Lunge"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes"]},
    {"name": "Curtsy Lunge", "aliases": ["Curtsy Lunges"], "category": "Legs", "primary_muscle": "Glutes", "secondary_muscles": ["Quads"]},
    {"name": "Cossack Squat", "aliases": ["Cossack Squats"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes", "Adductors"]},
    {"name": "Single-Leg Hip Thrust", "aliases": ["Single Leg Hip Thrust", "B-Stance Hip Thrust"], "category": "Legs", "primary_muscle": "Glutes", "secondary_muscles": ["Hamstrings"]},
    {"name": "Lying Leg Curl", "aliases": ["Lying Hamstring Curl", "Prone Leg Curl", "Lying Leg Curls"], "category": "Legs", "primary_muscle": "Hamstrings", "secondary_muscles": ["Calves"]},
    {"name": "Seated Leg Curl", "aliases": ["Seated Hamstring Curl", "Seated Leg Curls"], "category": "Legs", "primary_muscle": "Hamstrings", "secondary_muscles": ["Calves"]},
    {"name": "Nordic Hamstring Curl", "aliases": ["Nordic Curl", "Nordic Ham Curl", "Nordics"], "category": "Legs", "primary_muscle": "Hamstrings", "secondary_muscles": ["Calves"]},
    {"name": "Glute Ham Raise", "aliases": ["GHR", "Glute-Ham Raise"], "category": "Legs", "primary_muscle": "Hamstrings", "secondary_muscles": ["Glutes"]},
    {"name": "Cable Pull-Through", "aliases": ["Pull-Through", "Cable Pull Through", "Rope Pull-Through"], "category": "Legs", "primary_muscle": "Glutes", "secondary_muscles": ["Hamstrings"]},
    {"name": "Back Extension", "aliases": ["Hyperextension", "Hyperextensions", "45 Degree Back Extension", "Back Extensions"], "category": "Pull", "primary_muscle": "Lower Back", "secondary_muscles": ["Glutes", "Hamstrings"]},
    {"name": "Kettlebell Swing", "aliases": ["KB Swing", "Russian Kettlebell Swing", "Kettlebell Swings"], "category": "Legs", "primary_muscle": "Glutes", "secondary_muscles": ["Hamstrings", "Core"]},
    {"name": "Cable Glute Kickback", "aliases": ["Glute Kickback", "Cable Glute Kickbacks", "Donkey Kick"], "category": "Legs", "primary_muscle": "Glutes", "secondary_muscles": []},
    {"name": "Pendlay Row", "aliases": ["Pendlay Rows", "Dead-Stop Row"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Biceps"]},
    {"name": "Meadows Row", "aliases": ["Landmine Row", "Meadows Rows"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Biceps"]},
    {"name": "Seal Row", "aliases": ["Seal Rows", "Bench Seal Row"], "category": "Pull", "primary_muscle": "Back", "secondary_muscles": ["Biceps"]},
    {"name": "Floor Press", "aliases": ["Barbell Floor Press", "Dumbbell Floor Press", "DB Floor Press"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": ["Triceps"]},
    {"name": "Dumbbell Pullover", "aliases": ["DB Pullover", "Pullover", "Cross-Bench Pullover"], "category": "Push", "primary_muscle": "Chest", "secondary_muscles": ["Lats"]},
    {"name": "Reverse Curl", "aliases": ["Reverse Barbell Curl", "Reverse Grip Curl", "Reverse Curls"], "category": "Pull", "primary_muscle": "Forearms", "secondary_muscles": ["Biceps"]},
    {"name": "Cable Hammer Curl", "aliases": ["Rope Hammer Curl", "Rope Curl"], "category": "Pull", "primary_muscle": "Biceps", "secondary_muscles": ["Forearms"]},
    {"name": "Leg Press Calf Raise", "aliases": ["Calf Press", "Leg Press Calf Press"], "category": "Legs", "primary_muscle": "Calves", "secondary_muscles": []},
    {"name": "Donkey Calf Raise", "aliases": ["Donkey Calf Raises"], "category": "Legs", "primary_muscle": "Calves", "secondary_muscles": []},
    {"name": "Upright Row", "aliases": ["Barbell Upright Row", "Cable Upright Row", "Dumbbell Upright Row", "Upright Rows"], "category": "Pull", "primary_muscle": "Traps", "secondary_muscles": ["Side Delts"]},
    {"name": "Reverse Wrist Curl", "aliases": ["Wrist Extension", "Reverse Wrist Curls", "Wrist Extensions"], "category": "Accessories", "primary_muscle": "Forearms", "secondary_muscles": []},
    {"name": "Incline Cable Fly", "aliases": ["Low-to-High Cable Fly", "Low Cable Fly", "Incline Cable Flyes"], "category": "Push", "primary_muscle": "Upper Chest", "secondary_muscles": []},
    {"name": "Pistol Squat", "aliases": ["Single-Leg Squat", "Pistol Squats"], "category": "Legs", "primary_muscle": "Quads", "secondary_muscles": ["Glutes", "Core"]},
    {"name": "Sit-ups", "aliases": ["Sit-up", "Situps", "Sit Ups"], "category": "Core", "primary_muscle": "Abs", "secondary_muscles": []},
]

# Names that already ship in the seed and are only re-added defensively; their
# downgrade should NOT delete them, since other migrations/seed own them.
_PREEXISTING = {"Romanian Deadlift", "Leg Curl", "Good Mornings"}


def _insert_exercise(conn, name, canonical_id, ex_data, now):
    """Insert one exercise row if a row with that name doesn't already exist."""
    existing = conn.execute(
        text("SELECT id FROM exercises WHERE name = :name"),
        {"name": name},
    ).fetchone()
    if existing:
        return
    secondary_muscles_str = str(ex_data["secondary_muscles"]).replace("'", '"')
    conn.execute(
        text("""
            INSERT INTO exercises (id, name, canonical_id, category, primary_muscle,
                                   secondary_muscles, is_custom, created_at, updated_at)
            VALUES (:id, :name, :canonical_id, :category, :primary_muscle,
                    :secondary_muscles, false, :created_at, :updated_at)
        """),
        {
            "id": str(uuid.uuid4()),
            "name": name,
            "canonical_id": canonical_id,
            "category": ex_data["category"],
            "primary_muscle": ex_data["primary_muscle"],
            "secondary_muscles": secondary_muscles_str,
            "created_at": now,
            "updated_at": now,
        },
    )


def upgrade():
    conn = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()

    for ex_data in RESTORED_EXERCISES:
        # Reuse the existing canonical_id if the canonical name is already present
        # so any restored aliases attach to the same group.
        row = conn.execute(
            text("SELECT canonical_id FROM exercises WHERE name = :name"),
            {"name": ex_data["name"]},
        ).fetchone()
        canonical_id = row[0] if row and row[0] else str(uuid.uuid4())

        _insert_exercise(conn, ex_data["name"], canonical_id, ex_data, now)
        for alias in ex_data.get("aliases", []):
            _insert_exercise(conn, alias, canonical_id, ex_data, now)


def downgrade():
    conn = op.get_bind()

    for ex_data in RESTORED_EXERCISES:
        if ex_data["name"] in _PREEXISTING:
            # Owned by the seed / earlier migrations — leave in place.
            continue
        names = [ex_data["name"], *ex_data.get("aliases", [])]
        for name in names:
            conn.execute(
                text("DELETE FROM exercises WHERE name = :name AND is_custom = false"),
                {"name": name},
            )
