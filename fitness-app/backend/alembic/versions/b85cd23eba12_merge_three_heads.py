"""Merge three heads: expanded_exercises, workout_client_id, workout_cascade_fks

Three parallel branches accumulated on top of add_composite_indexes with no
merge. `alembic upgrade head` fails with "Multiple head revisions are
present" until they're unified, which blocks every Railway deploy.

Revision ID: b85cd23eba12
Revises: add_expanded_exercises, add_workout_client_id, add_workout_cascade_fks
Create Date: 2026-04-20 20:17:00.000000

"""


# revision identifiers, used by Alembic.
revision = 'b85cd23eba12'
down_revision = (
    'add_expanded_exercises',
    'add_workout_client_id',
    'add_workout_cascade_fks',
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
