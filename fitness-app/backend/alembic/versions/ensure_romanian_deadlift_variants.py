"""Ensure bilateral and single-leg Romanian Deadlift are separate exercises

"Single Leg Romanian Deadlift" was originally split out of the bilateral RDL by
hand (it only ever landed in ``seed_exercises.py``, never in a migration), so
databases that were migrated rather than freshly seeded can be missing it — or
worse, have it sharing a canonical_id with the barbell "Romanian Deadlift",
which merges their PR/e1RM tracking and hides one of the two from the exercise
picker.

This migration idempotently guarantees both movements exist as their own
canonical groups, each with its aliases, so a two-leg barbell RDL and a
single-leg dumbbell RDL are logged and PR-tracked separately.

Revision ID: ensure_rdl_variants
Revises: add_mile_splits
Create Date: 2026-08-08

"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = 'ensure_rdl_variants'
down_revision = 'add_mile_splits'
branch_labels = None
depends_on = None


BILATERAL = {
    "name": "Romanian Deadlift",
    "aliases": ["RDL", "Stiff-Leg Deadlift"],
    "category": "Pull",
    "primary_muscle": "Hamstrings",
    "secondary_muscles": ["Back", "Glutes"],
}

SINGLE_LEG = {
    "name": "Single Leg Romanian Deadlift",
    "aliases": ["Single Leg RDL", "SL RDL", "One Leg RDL"],
    "category": "Pull",
    "primary_muscle": "Hamstrings",
    "secondary_muscles": ["Glutes", "Core"],
}


def _canonical_id_for(conn, names):
    """Return the canonical_id already used by any of ``names``, if any."""
    for name in names:
        row = conn.execute(
            text("SELECT canonical_id FROM exercises WHERE name = :name AND is_custom = false"),
            {"name": name},
        ).fetchone()
        if row and row[0]:
            return row[0]
    return None


def _upsert_group(conn, ex_data, canonical_id, now):
    """Insert any missing row of a group and pin every row to canonical_id."""
    secondary_muscles_str = str(ex_data["secondary_muscles"]).replace("'", '"')

    for name in [ex_data["name"], *ex_data["aliases"]]:
        existing = conn.execute(
            text("SELECT id FROM exercises WHERE name = :name AND is_custom = false"),
            {"name": name},
        ).fetchone()

        if existing:
            conn.execute(
                text("""
                    UPDATE exercises SET canonical_id = :canonical_id, updated_at = :updated_at
                    WHERE id = :id AND (canonical_id IS NULL OR canonical_id != :canonical_id)
                """),
                {"canonical_id": canonical_id, "updated_at": now, "id": existing[0]},
            )
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

    # Keep whatever canonical_id the bilateral group already uses so existing
    # PRs and workout history stay grouped where they are.
    bilateral_id = _canonical_id_for(
        conn, [BILATERAL["name"], *BILATERAL["aliases"]]
    ) or str(uuid.uuid4())

    single_leg_id = _canonical_id_for(conn, [SINGLE_LEG["name"], *SINGLE_LEG["aliases"]])
    # A single-leg group sharing the bilateral canonical_id is the merge we're
    # undoing — mint a fresh id for it.
    if not single_leg_id or single_leg_id == bilateral_id:
        single_leg_id = str(uuid.uuid4())

    _upsert_group(conn, BILATERAL, bilateral_id, now)
    _upsert_group(conn, SINGLE_LEG, single_leg_id, now)


def downgrade():
    # Both movements ship in the seed library and either may already carry
    # logged workouts, so there is nothing safe to remove here.
    pass
