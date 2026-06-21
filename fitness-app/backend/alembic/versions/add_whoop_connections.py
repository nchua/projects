"""Add whoop_connections table for WHOOP API OAuth (Phase 1 wearable HR)

Stores a user's WHOOP OAuth tokens (encrypted at rest — the *_encrypted columns
hold Fernet ciphertext, never plaintext) so the backend can pull their recent
WHOOP workouts and backfill session-level HR. One connection per user
(user_id is unique).

Chained off the wearable-HR foundation head (add_wearable_hr).

Revision ID: add_whoop_connections
Revises: add_wearable_hr
Create Date: 2026-06-21 00:30:00.000000

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_whoop_connections'
down_revision = 'add_wearable_hr'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'whoop_connections',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('access_token_encrypted', sa.Text(), nullable=True),
        sa.Column('refresh_token_encrypted', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('whoop_user_id', sa.String(), nullable=True),
        sa.Column('scope', sa.String(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # One WHOOP connection per user.
    op.create_index(
        'ix_whoop_connections_user_id', 'whoop_connections', ['user_id'], unique=True
    )
    op.create_index(
        'ix_whoop_connections_whoop_user_id', 'whoop_connections', ['whoop_user_id']
    )


def downgrade() -> None:
    op.drop_index('ix_whoop_connections_whoop_user_id', table_name='whoop_connections')
    op.drop_index('ix_whoop_connections_user_id', table_name='whoop_connections')
    op.drop_table('whoop_connections')
