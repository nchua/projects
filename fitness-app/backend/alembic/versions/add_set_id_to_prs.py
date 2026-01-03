"""Add set_id to prs table

Revision ID: add_set_id_to_prs
Revises: 949a78c76812
Create Date: 2026-01-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_set_id_to_prs'
down_revision = '949a78c76812'
branch_labels = None
depends_on = None


def upgrade():
    # Add set_id column to prs table
    op.add_column('prs', sa.Column('set_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_prs_set_id'), 'prs', ['set_id'], unique=False)
    op.create_foreign_key('fk_prs_set_id', 'prs', 'sets', ['set_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_prs_set_id', 'prs', type_='foreignkey')
    op.drop_index(op.f('ix_prs_set_id'), table_name='prs')
    op.drop_column('prs', 'set_id')
