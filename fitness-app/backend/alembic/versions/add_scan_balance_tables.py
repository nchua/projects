"""add scan_balances and purchase_records tables

Revision ID: a1b2c3d4e5f6
Revises: 0643f4677e6e
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0643f4677e6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create scan_balances table
    op.create_table(
        'scan_balances',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('scan_credits', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('has_unlimited', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('free_scans_reset_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_scan_balances_user_id', 'scan_balances', ['user_id'], unique=True)

    # Create purchase_records table
    op.create_table(
        'purchase_records',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('product_id', sa.String(), nullable=False),
        sa.Column('transaction_id', sa.String(), nullable=False, unique=True),
        sa.Column('credits_added', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('purchase_type', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_purchase_records_user_id', 'purchase_records', ['user_id'])
    op.create_index('ix_purchase_records_transaction_id', 'purchase_records', ['transaction_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_purchase_records_transaction_id', table_name='purchase_records')
    op.drop_index('ix_purchase_records_user_id', table_name='purchase_records')
    op.drop_table('purchase_records')
    op.drop_index('ix_scan_balances_user_id', table_name='scan_balances')
    op.drop_table('scan_balances')
