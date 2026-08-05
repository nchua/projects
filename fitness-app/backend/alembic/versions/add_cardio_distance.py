"""Add activity_type + distance_meters to workout_sessions, backfill from notes

HealthKit cardio imports previously stashed distance in the notes string
("Outdoor Run - Apple Watch | Distance: 5012m"). This adds real columns and
backfills them by parsing the notes of existing HealthKit-imported sessions.

Revision ID: add_cardio_distance
Revises: add_hunt_name
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "add_cardio_distance"
down_revision = "add_hunt_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workout_sessions", sa.Column("activity_type", sa.String(length=64), nullable=True))
    op.add_column("workout_sessions", sa.Column("distance_meters", sa.Float(), nullable=True))
    # Exact cardio duration for pace math (duration_minutes is rounded).
    op.add_column("workout_sessions", sa.Column("duration_seconds", sa.Integer(), nullable=True))

    # Backfill from the notes convention used by the HealthKit import:
    #   "<activity_type> - Apple Watch | Distance: <n>m"
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text(
            r"""
            UPDATE workout_sessions
            SET distance_meters = CAST(substring(notes FROM 'Distance: (\d+)m') AS FLOAT)
            WHERE hk_uuid IS NOT NULL
              AND distance_meters IS NULL
              AND notes ~ 'Distance: \d+m'
            """
        ))
        conn.execute(sa.text(
            r"""
            UPDATE workout_sessions
            SET activity_type = substring(notes FROM '^(.*) - Apple Watch')
            WHERE hk_uuid IS NOT NULL
              AND activity_type IS NULL
              AND notes ~ ' - Apple Watch'
            """
        ))
    else:
        # SQLite (tests/local): parse in Python — tiny datasets only.
        import re
        rows = conn.execute(sa.text(
            "SELECT id, notes FROM workout_sessions "
            "WHERE hk_uuid IS NOT NULL AND notes IS NOT NULL"
        )).fetchall()
        for row_id, notes in rows:
            dist = re.search(r"Distance: (\d+)m", notes)
            act = re.match(r"^(.*) - Apple Watch", notes)
            if dist or act:
                conn.execute(
                    sa.text(
                        "UPDATE workout_sessions SET "
                        "distance_meters = COALESCE(distance_meters, :d), "
                        "activity_type = COALESCE(activity_type, :a) "
                        "WHERE id = :i"
                    ),
                    {
                        "d": float(dist.group(1)) if dist else None,
                        "a": act.group(1) if act else None,
                        "i": row_id,
                    },
                )


def downgrade() -> None:
    op.drop_column("workout_sessions", "duration_seconds")
    op.drop_column("workout_sessions", "distance_meters")
    op.drop_column("workout_sessions", "activity_type")
