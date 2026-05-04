"""Restore foundational exercises wrongly consolidated as aliases

Romanian Deadlift was being shadowed by 'Stiff-Leg Deadlift' (longer name wins
in the API dedup logic at app/api/exercises.py), so the picker showed
'Stiff-Leg Deadlift' instead of 'Romanian Deadlift'. Same shape problem with
'Seated Shoulder Press', which was an alias of 'Seated Dumbbell Press' and
disappeared from the picker entirely.

This migration:
  1. Detaches 'Stiff-Leg Deadlift' from the Romanian Deadlift canonical group
     by giving it a fresh canonical_id, then ensures 'Stiff Leg Deadlift' and
     'SLDL' aliases share that new canonical_id.
  2. Detaches 'Seated Shoulder Press' from the Seated Dumbbell Press canonical
     group by giving it a fresh canonical_id, then adds 'Seated OHP' and
     'Seated Press' aliases under it.

Revision ID: restore_foundational_exercises
Revises: b85cd23eba12
Create Date: 2026-05-04

"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from alembic import op

revision = 'restore_foundational_exercises'
down_revision = 'b85cd23eba12'
branch_labels = None
depends_on = None


def _ensure_alias(conn, name, canonical_id, category, primary_muscle, secondary_muscles_json, now):
    existing = conn.execute(
        text("SELECT id, canonical_id FROM exercises WHERE name = :name AND is_custom = false"),
        {"name": name},
    ).fetchone()

    if existing:
        if existing[1] != canonical_id:
            conn.execute(
                text("UPDATE exercises SET canonical_id = :cid, updated_at = :now WHERE id = :id"),
                {"cid": canonical_id, "id": existing[0], "now": now},
            )
        return

    conn.execute(
        text(
            """
            INSERT INTO exercises (id, name, canonical_id, category, primary_muscle,
                                   secondary_muscles, is_custom, created_at, updated_at)
            VALUES (:id, :name, :canonical_id, :category, :primary_muscle,
                    :secondary_muscles, false, :created_at, :updated_at)
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "name": name,
            "canonical_id": canonical_id,
            "category": category,
            "primary_muscle": primary_muscle,
            "secondary_muscles": secondary_muscles_json,
            "created_at": now,
            "updated_at": now,
        },
    )


def _split_canonical(conn, alias_name, category, primary_muscle, secondary_muscles_json,
                     extra_aliases, now):
    """Promote an alias row into its own canonical and re-link its aliases."""
    row = conn.execute(
        text("SELECT id FROM exercises WHERE name = :name AND is_custom = false"),
        {"name": alias_name},
    ).fetchone()

    if row:
        new_canonical_id = str(uuid.uuid4())
        conn.execute(
            text(
                "UPDATE exercises SET canonical_id = :cid, category = :cat, "
                "primary_muscle = :pm, secondary_muscles = :sm, updated_at = :now "
                "WHERE id = :id"
            ),
            {
                "cid": new_canonical_id,
                "cat": category,
                "pm": primary_muscle,
                "sm": secondary_muscles_json,
                "now": now,
                "id": row[0],
            },
        )
    else:
        new_canonical_id = str(uuid.uuid4())
        conn.execute(
            text(
                """
                INSERT INTO exercises (id, name, canonical_id, category, primary_muscle,
                                       secondary_muscles, is_custom, created_at, updated_at)
                VALUES (:id, :name, :canonical_id, :category, :primary_muscle,
                        :secondary_muscles, false, :created_at, :updated_at)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "name": alias_name,
                "canonical_id": new_canonical_id,
                "category": category,
                "primary_muscle": primary_muscle,
                "secondary_muscles": secondary_muscles_json,
                "created_at": now,
                "updated_at": now,
            },
        )

    for alias in extra_aliases:
        _ensure_alias(
            conn, alias, new_canonical_id, category, primary_muscle, secondary_muscles_json, now
        )


def upgrade():
    conn = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()

    _split_canonical(
        conn,
        alias_name="Stiff-Leg Deadlift",
        category="Pull",
        primary_muscle="Hamstrings",
        secondary_muscles_json='["Back", "Glutes"]',
        extra_aliases=["Stiff Leg Deadlift", "SLDL"],
        now=now,
    )

    _split_canonical(
        conn,
        alias_name="Seated Shoulder Press",
        category="Push",
        primary_muscle="Shoulders",
        secondary_muscles_json='["Triceps"]',
        extra_aliases=["Seated OHP", "Seated Press"],
        now=now,
    )


def downgrade():
    conn = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()

    rdl = conn.execute(
        text(
            "SELECT canonical_id FROM exercises "
            "WHERE name = 'Romanian Deadlift' AND is_custom = false"
        )
    ).fetchone()
    if rdl:
        conn.execute(
            text(
                "UPDATE exercises SET canonical_id = :cid, updated_at = :now "
                "WHERE name IN ('Stiff-Leg Deadlift', 'Stiff Leg Deadlift', 'SLDL') "
                "AND is_custom = false"
            ),
            {"cid": rdl[0], "now": now},
        )

    sdp = conn.execute(
        text(
            "SELECT canonical_id FROM exercises "
            "WHERE name = 'Seated Dumbbell Press' AND is_custom = false"
        )
    ).fetchone()
    if sdp:
        conn.execute(
            text(
                "UPDATE exercises SET canonical_id = :cid, updated_at = :now "
                "WHERE name IN ('Seated Shoulder Press', 'Seated OHP', 'Seated Press') "
                "AND is_custom = false"
            ),
            {"cid": sdp[0], "now": now},
        )
