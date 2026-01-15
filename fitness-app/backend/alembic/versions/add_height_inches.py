"""Add height_inches to user_profiles

Revision ID: add_height_inches
Revises: add_one_arm_exercises
Create Date: 2026-01-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_height_inches'
down_revision = 'add_one_arm_exercises'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('user_profiles', sa.Column('height_inches', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('user_profiles', 'height_inches')
