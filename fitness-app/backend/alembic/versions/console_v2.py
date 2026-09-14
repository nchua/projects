"""Owner console v2 — app_settings table + users.last_login_at (console v2 spec §6.5–§6.7)

``app_settings`` holds the console overrides of registry keys (one row per
key; a missing row means the env / code value applies). ``users.last_login_at``
feeds ``last_active`` (login leg); existing users read NULL until their next
login and fall back to workouts / scans.

Idempotent: inspector-guarded; SQLite runs the column add in batch mode. No
data changes.

Revision ID: console_v2
Revises: purchase_verification
Create Date: 2026-09-13

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "console_v2"
down_revision = "purchase_verification"
branch_labels = None
depends_on = None

SETTINGS_TABLE = "app_settings"
USERS_TABLE = "users"
LOGIN_COLUMN = "last_login_at"


def _inspector():
    return sa.inspect(op.get_bind())


def _user_columns() -> set:
    return {c["name"] for c in _inspector().get_columns(USERS_TABLE)}


def _batch_users():
    """Batch mode so SQLite (tests) recreates the table; Postgres runs plain ALTERs."""
    sqlite = op.get_bind().dialect.name == "sqlite"
    return op.batch_alter_table(USERS_TABLE, recreate="always" if sqlite else "auto")


def upgrade():
    if SETTINGS_TABLE not in _inspector().get_table_names():
        op.create_table(
            SETTINGS_TABLE,
            sa.Column("key", sa.String(), primary_key=True),
            sa.Column("value", sa.JSON(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.String(), nullable=True),
        )
    if LOGIN_COLUMN not in _user_columns():
        with _batch_users() as batch_op:
            batch_op.add_column(sa.Column(LOGIN_COLUMN, sa.DateTime(), nullable=True))


def downgrade():
    if LOGIN_COLUMN in _user_columns():
        with _batch_users() as batch_op:
            batch_op.drop_column(LOGIN_COLUMN)
    if SETTINGS_TABLE in _inspector().get_table_names():
        op.drop_table(SETTINGS_TABLE)
