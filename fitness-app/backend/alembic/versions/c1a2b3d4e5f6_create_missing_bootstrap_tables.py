"""Create missing bootstrap tables (user_quests, quest_definitions, user_progress, etc.)

The alembic chain previously assumed these tables were created via
``Base.metadata.create_all()`` on app startup, so no migration ever created
them. The "Alembic up/down/up on Postgres" CI job exposed the gap because
``b3c7e2f91a45_add_completed_by_workout_id_to_user_quests.py`` tries to
``add_column`` on ``user_quests`` before any migration creates it.

This migration is idempotent: it inspects the live DB and skips tables that
already exist. On already-bootstrapped prod DBs (Railway) the tables exist
so this is a no-op; on a fresh Postgres (CI) it creates them from scratch.

Revision ID: c1a2b3d4e5f6
Revises: da26ee9e5945
Create Date: 2026-04-19 12:00:00.000000

"""
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.exc import NoInspectionAvailable

from alembic import op

# revision identifiers, used by Alembic.
revision = "c1a2b3d4e5f6"
down_revision = "da26ee9e5945"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    """Return tables already present in the live DB.

    In ``--sql`` (offline) mode ``op.get_bind()`` returns a MockConnection
    that can't be inspected. In that case we return an empty set so every
    ``CREATE TABLE`` is emitted — that's the intended behavior for
    generating a fresh-DB SQL script.
    """
    bind = op.get_bind()
    try:
        insp = inspect(bind)
    except NoInspectionAvailable:
        return set()
    return set(insp.get_table_names())


def upgrade() -> None:
    existing = _existing_tables()

    # user_progress: XP / level / rank tracking
    if "user_progress" not in existing:
        op.create_table(
            "user_progress",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("total_xp", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("rank", sa.String(), nullable=False, server_default="E"),
            sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("longest_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_workout_date", sa.Date(), nullable=True),
            sa.Column("total_workouts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_volume_lb", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_prs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )

    # daily_activity: HealthKit / Whoop sync
    if "daily_activity" not in existing:
        op.create_table(
            "daily_activity",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("source", sa.String(), nullable=False, server_default="apple_fitness"),
            sa.Column("steps", sa.Integer(), nullable=True),
            sa.Column("active_calories", sa.Integer(), nullable=True),
            sa.Column("total_calories", sa.Integer(), nullable=True),
            sa.Column("active_minutes", sa.Integer(), nullable=True),
            sa.Column("exercise_minutes", sa.Integer(), nullable=True),
            sa.Column("stand_hours", sa.Integer(), nullable=True),
            sa.Column("move_calories", sa.Integer(), nullable=True),
            sa.Column("strain", sa.Float(), nullable=True),
            sa.Column("recovery_score", sa.Integer(), nullable=True),
            sa.Column("hrv", sa.Integer(), nullable=True),
            sa.Column("resting_heart_rate", sa.Integer(), nullable=True),
            sa.Column("sleep_hours", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "date", "source", name="unique_user_date_source"),
        )
        op.create_index(
            op.f("ix_daily_activity_user_id"), "daily_activity", ["user_id"], unique=False
        )
        op.create_index(
            op.f("ix_daily_activity_date"), "daily_activity", ["date"], unique=False
        )

    # quest_definitions: master list of quests
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

    # user_quests: user's assigned quest progress
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
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["quest_id"], ["quest_definitions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        # Note: the ix_user_quests_user_date composite index is created by the
        # later migration ``add_composite_indexes`` (f8a2c3d4e5b6). We don't
        # create it here to avoid duplicate-index errors in that migration.

    # achievement_definitions: master list of achievements
    if "achievement_definitions" not in existing:
        op.create_table(
            "achievement_definitions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("category", sa.String(), nullable=False),
            sa.Column("icon", sa.String(), nullable=False),
            sa.Column("xp_reward", sa.Integer(), nullable=False, server_default="50"),
            sa.Column("rarity", sa.String(), nullable=False, server_default="common"),
            sa.Column("requirement_type", sa.String(), nullable=True),
            sa.Column("requirement_value", sa.Integer(), nullable=True),
            sa.Column("requirement_exercise", sa.String(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    # user_achievements: achievements unlocked by users
    if "user_achievements" not in existing:
        op.create_table(
            "user_achievements",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("user_progress_id", sa.String(), nullable=False),
            sa.Column("achievement_id", sa.String(), nullable=False),
            sa.Column("unlocked_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["user_progress_id"], ["user_progress.id"]),
            sa.ForeignKeyConstraint(["achievement_id"], ["achievement_definitions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    # Drop in reverse dependency order. Only drop if this migration owns them,
    # but since we can't easily track that, attempt unconditional drops.
    # In CI (fresh DB) this is fine; on prod we don't run downgrade.
    op.drop_table("user_achievements")
    op.drop_table("achievement_definitions")
    op.drop_table("user_quests")
    op.drop_table("quest_definitions")
    op.drop_index(op.f("ix_daily_activity_date"), table_name="daily_activity")
    op.drop_index(op.f("ix_daily_activity_user_id"), table_name="daily_activity")
    op.drop_table("daily_activity")
    op.drop_table("user_progress")
