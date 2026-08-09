"""Backfill alias rows for the lying tricep extension / skull crusher group

The library now names this movement "Lying Tricep Extension" (it reads as a
sibling of "Overhead Tricep Extension" in the picker) with "Skull Crushers" as
an alias. Both of those rows already exist in every database; the singular and
plural-triceps spellings do not, and the picker searches alias rows, so add
them to the group.

Revision ID: lying_tricep_aliases
Revises: ensure_rdl_variants
Create Date: 2026-08-09

"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = 'lying_tricep_aliases'
down_revision = 'ensure_rdl_variants'
branch_labels = None
depends_on = None


GROUP_NAMES = [
    "Lying Tricep Extension",
    "Skull Crushers",
    "Skull Crusher",
    "EZ Bar Skull Crusher",
    "Lying Triceps Extension",
]

# Names this migration introduces; only these are safe to remove on downgrade.
ADDED_NAMES = ["Skull Crusher", "Lying Triceps Extension"]


def upgrade():
    conn = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()

    canonical_id = None
    for name in GROUP_NAMES:
        row = conn.execute(
            text("SELECT canonical_id FROM exercises WHERE name = :name AND is_custom = false"),
            {"name": name},
        ).fetchone()
        if row and row[0]:
            canonical_id = row[0]
            break

    if canonical_id is None:
        # Group absent entirely (a database seeded before this movement
        # existed) — seed_exercises.py owns creating it from scratch.
        canonical_id = str(uuid.uuid4())

    for name in GROUP_NAMES:
        existing = conn.execute(
            text("SELECT id FROM exercises WHERE name = :name AND is_custom = false"),
            {"name": name},
        ).fetchone()
        if existing:
            continue
        conn.execute(
            text("""
                INSERT INTO exercises (id, name, canonical_id, category, primary_muscle,
                                       secondary_muscles, is_custom, created_at, updated_at)
                VALUES (:id, :name, :canonical_id, 'Push', 'Triceps',
                        '[]', false, :created_at, :updated_at)
            """),
            {
                "id": str(uuid.uuid4()),
                "name": name,
                "canonical_id": canonical_id,
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade():
    conn = op.get_bind()
    for name in ADDED_NAMES:
        # Only drop rows nothing has been logged against.
        conn.execute(
            text("""
                DELETE FROM exercises
                WHERE name = :name AND is_custom = false
                  AND id NOT IN (SELECT exercise_id FROM workout_exercises)
                  AND id NOT IN (SELECT exercise_id FROM prs)
            """),
            {"name": name},
        )
