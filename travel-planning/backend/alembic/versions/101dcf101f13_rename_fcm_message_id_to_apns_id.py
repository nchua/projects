"""rename fcm_message_id to apns_id

Revision ID: 101dcf101f13
Revises: aeba3e0dd4b6
Create Date: 2026-03-22 15:52:56.584519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '101dcf101f13'
down_revision: Union[str, None] = 'aeba3e0dd4b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "notifications_log",
        "fcm_message_id",
        new_column_name="apns_id",
    )


def downgrade() -> None:
    op.alter_column(
        "notifications_log",
        "apns_id",
        new_column_name="fcm_message_id",
    )
