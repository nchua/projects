"""Repair: ensure user_quests.completed_by_workout_id exists (prod schema drift)

Production's ``alembic_version`` is stamped past ``b3c7e2f91a45`` (which adds
``user_quests.completed_by_workout_id``), but that migration's DDL never ran on
prod — so the column is missing while ``update_quest_progress`` selects it,
500-ing every workout create (strength and HealthKit cardio import).

``alembic upgrade head`` is a no-op there because the version is already stamped,
so this corrective migration idempotently adds the column + FK when absent. It is
a no-op anywhere the column already exists (local/test via model ``create_all``,
and the CI Postgres run where ``b3c7e2f91a45`` already added it).

Revision ID: repair_completed_by_workout_id
Revises: restore_pruned_exercises
Create Date: 2026-06-28
"""
import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = 'repair_completed_by_workout_id'
down_revision = 'restore_pruned_exercises'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in inspect(bind).get_columns("user_quests")}
    if "completed_by_workout_id" not in columns:
        op.add_column(
            "user_quests",
            sa.Column("completed_by_workout_id", sa.String(), nullable=True),
        )
        op.create_foreign_key(
            "fk_user_quests_completed_by_workout",
            "user_quests",
            "workout_sessions",
            ["completed_by_workout_id"],
            ["id"],
        )


def downgrade() -> None:
    # Corrective/no-op: the column's lifecycle is owned by b3c7e2f91a45's
    # up/down. Dropping here would double-drop on a normal downgrade chain.
    pass
