"""ARISE v3 foundations (0a) — set-level unit/warm-up columns + session load

sets.weight_lb is the unit-normalized weight every e1RM is computed from;
sets.is_bodyweight / is_warmup are the LogView v2 set flags (spec §7.5).
workout_sessions.training_load / load_estimated hold the per-session load
number the training-load service writes (spec §6.1).

Idempotent: every add is guarded by an inspector check and the backfill only
touches NULL rows, so a re-run after prod stamp drift is a no-op.

Revision ID: v3_sets_columns
Revises: workout_local_date
Create Date: 2026-09-05

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'v3_sets_columns'
down_revision = 'workout_local_date'
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    set_cols = _columns("sets")
    if "weight_lb" not in set_cols:
        op.add_column("sets", sa.Column("weight_lb", sa.Float(), nullable=True))
    if "is_bodyweight" not in set_cols:
        op.add_column(
            "sets",
            sa.Column("is_bodyweight", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "is_warmup" not in set_cols:
        op.add_column(
            "sets",
            sa.Column("is_warmup", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    session_cols = _columns("workout_sessions")
    if "training_load" not in session_cols:
        op.add_column("workout_sessions", sa.Column("training_load", sa.Float(), nullable=True))
    if "load_estimated" not in session_cols:
        op.add_column("workout_sessions", sa.Column("load_estimated", sa.Boolean(), nullable=True))

    # Backfill. No kg rows exist in prod today, but the CASE keeps it honest.
    # weight_unit is an Enum column (stored as the member name on Postgres),
    # so compare case-insensitively through a text cast.
    op.execute(
        "UPDATE sets SET weight_lb = "
        "CASE WHEN LOWER(CAST(weight_unit AS VARCHAR)) = 'kg' "
        "THEN weight * 2.20462 ELSE weight END "
        "WHERE weight_lb IS NULL"
    )


def downgrade():
    set_cols = _columns("sets")
    with op.batch_alter_table("sets") as batch_op:
        for col in ("is_warmup", "is_bodyweight", "weight_lb"):
            if col in set_cols:
                batch_op.drop_column(col)

    session_cols = _columns("workout_sessions")
    with op.batch_alter_table("workout_sessions") as batch_op:
        for col in ("load_estimated", "training_load"):
            if col in session_cols:
                batch_op.drop_column(col)
