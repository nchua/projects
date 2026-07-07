"""Drop dungeon and weekly-mission tables (ARISE v2 Phase 0)

Phase 0 removes the Dungeons system and Weekly Missions entirely (spec §3).
Goals survive (goals / goal_progress_snapshots are untouched), and the daily
quest tables (quest_definitions / user_quests) stay until Phase 1.

Idempotent: inspects the live DB and skips tables that don't exist, following
the c1a2b3d4e5f6_create_missing_bootstrap_tables.py pattern. Children are
dropped before parents to respect FKs.

Revision ID: drop_dungeon_mission_tables
Revises: repair_completed_by_workout_id
Create Date: 2026-07-06 12:00:00.000000

"""
from sqlalchemy import inspect
from sqlalchemy.exc import NoInspectionAvailable

from alembic import op

# revision identifiers, used by Alembic.
revision = "drop_dungeon_mission_tables"
down_revision = "repair_completed_by_workout_id"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    """Return tables already present in the live DB.

    In ``--sql`` (offline) mode ``op.get_bind()`` returns a MockConnection
    that can't be inspected. In that case we return an empty set so no DROP
    is emitted (dropping blindly in offline mode could fail on a fresh DB).
    """
    bind = op.get_bind()
    try:
        insp = inspect(bind)
    except NoInspectionAvailable:
        return set()
    return set(insp.get_table_names())


# Children first so FK constraints don't block the drops.
TABLES_TO_DROP = [
    "user_dungeon_objectives",
    "user_dungeons",
    "dungeon_objective_definitions",
    "dungeon_definitions",
    "exercise_prescriptions",
    "mission_workouts",
    "mission_goals",
    "weekly_missions",
]


def upgrade() -> None:
    existing = _existing_tables()
    for table in TABLES_TO_DROP:
        if table in existing:
            op.drop_table(table)


def downgrade() -> None:
    # No-op: the dungeon/mission systems were deleted from the codebase, so
    # there is nothing to restore these tables for (repo precedent for
    # destructive cleanups).
    pass
