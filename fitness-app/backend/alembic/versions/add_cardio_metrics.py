"""Add cardio metrics to workout_sessions

Revision ID: add_cardio_metrics
Revises: add_hunt_name
Create Date: 2026-07-26

Activity screenshots (Apple Health / WHOOP / Strava runs and rides) surface
distance, pace, elevation, cadence and power, but the extractor previously
discarded all of it and kept only duration/calories/heart rate. These columns
give those metrics a home.

All nullable so every existing session — strength and cardio alike — is
unaffected and no backfill is required. Values are stored in SI units
(metres, metres/second) regardless of what the source app displayed, so runs
logged in miles and kilometres remain directly comparable; clients format for
display.

Chained off add_hunt_name (the previous workout_sessions column change) rather
than opening a new branch, so the repository's existing head count is
unchanged.
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_cardio_metrics'
down_revision = 'add_hunt_name'
branch_labels = None
depends_on = None


CARDIO_COLUMNS = (
    ('distance_meters', sa.Float()),
    ('elevation_gain_meters', sa.Float()),
    ('avg_speed_mps', sa.Float()),
    ('avg_cadence_spm', sa.Integer()),
    ('avg_power_watts', sa.Integer()),
    ('active_calories', sa.Integer()),
    ('total_calories', sa.Integer()),
)


def upgrade() -> None:
    for name, type_ in CARDIO_COLUMNS:
        op.add_column(
            'workout_sessions',
            sa.Column(name, type_, nullable=True),
        )


def downgrade() -> None:
    for name, _type in reversed(CARDIO_COLUMNS):
        op.drop_column('workout_sessions', name)
