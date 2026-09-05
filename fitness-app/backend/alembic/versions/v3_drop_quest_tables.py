"""ARISE v3 Phase 4 — drop the retired daily-quest tables (spec §11)

``quest_definitions`` and ``user_quests`` outlived the quest system by two
phases: the day-stat helpers they hosted moved to ``workout_stats.py`` (W0)
and the ORM registration was removed from ``app/models/__init__.py`` (W3),
so nothing reads them any more.

Idempotent: inspector-guarded drops (children first), following the
``drop_dungeon_mission_tables`` pattern — a re-run on an already-dropped
schema is a no-op. Downgrade recreates minimal tables (also guarded) so the
older ``add_composite_indexes`` / bootstrap downgrades still find what they
drop; on SQLite (tests) and Postgres alike a second downgrade is a no-op.

Revision ID: v3_drop_quest_tables
Revises: v3_campaign_tables
Create Date: 2026-09-05

"""
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.exc import NoInspectionAvailable

from alembic import op

# revision identifiers, used by Alembic.
revision = "v3_drop_quest_tables"
down_revision = "v3_campaign_tables"
branch_labels = None
depends_on = None

# Children first so FK constraints don't block the drops.
TABLES_TO_DROP = ["user_quests", "quest_definitions"]


def _existing_tables() -> set[str]:
    """Tables present in the live DB (empty set in ``--sql`` offline mode)."""
    bind = op.get_bind()
    try:
        insp = inspect(bind)
    except NoInspectionAvailable:
        return set()
    return set(insp.get_table_names())


def upgrade() -> None:
    existing = _existing_tables()
    for table in TABLES_TO_DROP:
        if table in existing:
            op.drop_table(table)


def downgrade() -> None:
    existing = _existing_tables()
    if "quest_definitions" not in existing:
        op.create_table(
            "quest_definitions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("quest_type", sa.String(), nullable=False),
            sa.Column("target_value", sa.Integer(), nullable=False),
            sa.Column("target_exercise", sa.String(), nullable=True),
            sa.Column("xp_reward", sa.Integer(), nullable=False, server_default="25"),
            sa.Column("difficulty", sa.String(), nullable=False, server_default="normal"),
            sa.Column("is_daily", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if "user_quests" not in existing:
        op.create_table(
            "user_quests",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("quest_id", sa.String(), nullable=False),
            sa.Column("assigned_date", sa.Date(), nullable=False),
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_claimed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("claimed_at", sa.DateTime(), nullable=True),
            sa.Column("completed_by_workout_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["quest_id"], ["quest_definitions.id"]),
            sa.ForeignKeyConstraint(
                ["completed_by_workout_id"], ["workout_sessions.id"],
                name="fk_user_quests_completed_by_workout",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_user_quests_user_date", "user_quests", ["user_id", "assigned_date"]
        )
