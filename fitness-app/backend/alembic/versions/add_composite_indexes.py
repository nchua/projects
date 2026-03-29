"""Add composite indexes for user_quests and user_dungeons

Revision ID: f8a2c3d4e5b6
Revises: 6e16b5ba89d1
Create Date: 2026-03-29
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f8a2c3d4e5b6"
down_revision = "6e16b5ba89d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_user_quests_user_date",
        "user_quests",
        ["user_id", "assigned_date"],
    )
    op.create_index(
        "ix_user_dungeons_user_status",
        "user_dungeons",
        ["user_id", "status"],
    )


def downgrade():
    op.drop_index("ix_user_dungeons_user_status", table_name="user_dungeons")
    op.drop_index("ix_user_quests_user_date", table_name="user_quests")
