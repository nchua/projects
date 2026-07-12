"""Create user_directives table (ARISE v2 Phase 1, spec §5.3)

One System Directive per (user, local day). Idempotent: inspects the live DB
and skips creation if the table already exists, following the
c1a2b3d4e5f6_create_missing_bootstrap_tables.py pattern (memory: prod stamp
drift makes non-idempotent DDL bite silently).

Revision ID: add_user_directives
Revises: drop_dungeon_mission_tables
Create Date: 2026-07-12 12:00:00.000000

"""
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.exc import NoInspectionAvailable

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_user_directives"
down_revision = "drop_dungeon_mission_tables"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    """Return tables already present in the live DB.

    In ``--sql`` (offline) mode ``op.get_bind()`` returns a MockConnection
    that can't be inspected. In that case we return an empty set so the
    CREATE TABLE is emitted — the intended behavior for a fresh-DB script.
    """
    bind = op.get_bind()
    try:
        insp = inspect(bind)
    except NoInspectionAvailable:
        return set()
    return set(insp.get_table_names())


def upgrade() -> None:
    if "user_directives" in _existing_tables():
        return
    op.create_table(
        "user_directives",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("directive_type", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("xp_reward", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", name="unique_user_directive_date"),
    )
    op.create_index(
        op.f("ix_user_directives_user_id"), "user_directives", ["user_id"], unique=False
    )


def downgrade() -> None:
    if "user_directives" not in _existing_tables():
        return
    op.drop_index(op.f("ix_user_directives_user_id"), table_name="user_directives")
    op.drop_table("user_directives")
