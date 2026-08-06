"""Add mile_splits to workout_sessions

Per-mile split times (seconds per completed mile, JSON list) for cardio
sessions, computed on-device from HealthKit distance samples. Existing rows
stay NULL; the iOS 90-day re-sync backfills them the same way it backfills
distance.

Revision ID: add_mile_splits
Revises: add_cardio_distance
Create Date: 2026-08-05
"""
import sqlalchemy as sa

from alembic import op

revision = "add_mile_splits"
down_revision = "add_cardio_distance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workout_sessions", sa.Column("mile_splits", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("workout_sessions", "mile_splits")
