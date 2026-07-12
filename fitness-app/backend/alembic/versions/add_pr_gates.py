"""Create pr_gates table (ARISE v2 Phase 2, spec §6.5)

Chains off add_user_directives to keep a single alembic head (memory: the
multi-head failure mode deploys "green" on Railway while the old instance
keeps serving). Idempotent like its predecessors.

Revision ID: add_pr_gates
Revises: add_user_directives
Create Date: 2026-07-12 18:00:00.000000

"""
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.exc import NoInspectionAvailable

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_pr_gates"
down_revision = "add_user_directives"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    """Return tables already present in the live DB (empty set offline)."""
    bind = op.get_bind()
    try:
        insp = inspect(bind)
    except NoInspectionAvailable:
        return set()
    return set(insp.get_table_names())


def upgrade() -> None:
    if "pr_gates" in _existing_tables():
        return
    op.create_table(
        "pr_gates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("exercise_id", sa.String(), nullable=False),
        sa.Column("rank", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("target_weight", sa.Float(), nullable=False),
        sa.Column("target_reps", sa.Integer(), nullable=False),
        sa.Column("target_e1rm", sa.Float(), nullable=False),
        sa.Column("baseline_e1rm", sa.Float(), nullable=False),
        sa.Column("projected_e1rm", sa.Float(), nullable=False),
        sa.Column("weekly_slope", sa.Float(), nullable=False),
        sa.Column("condition_at_spawn", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("spawned_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("cleared_at", sa.DateTime(), nullable=True),
        sa.Column("cleared_by_set_id", sa.String(), nullable=True),
        sa.Column("xp_awarded", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"]),
        sa.ForeignKeyConstraint(["cleared_by_set_id"], ["sets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pr_gates_user_status", "pr_gates", ["user_id", "status"], unique=False)


def downgrade() -> None:
    if "pr_gates" not in _existing_tables():
        return
    op.drop_index("ix_pr_gates_user_status", table_name="pr_gates")
    op.drop_table("pr_gates")
