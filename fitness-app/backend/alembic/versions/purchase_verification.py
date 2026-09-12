"""App Store JWS verification — purchase_records verification columns (spec §6.5)

Adds ``verified`` (NOT NULL, default false), ``environment``,
``original_transaction_id`` and ``purchase_date`` to ``purchase_records``.
Existing rows stay ``verified = false``: they were recorded from client
claims before verification shipped.

Idempotent: every column add is inspector-guarded; SQLite runs in batch mode.

Revision ID: purchase_verification
Revises: admin_seed_backfill
Create Date: 2026-09-12

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "purchase_verification"
down_revision = "admin_seed_backfill"
branch_labels = None
depends_on = None

TABLE = "purchase_records"


def _columns() -> list:
    """Fresh Column objects per call (a Column cannot be attached to two tables)."""
    return [
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("environment", sa.String(), nullable=True),
        sa.Column("original_transaction_id", sa.String(), nullable=True),
        sa.Column("purchase_date", sa.DateTime(), nullable=True),
    ]


def _existing_columns() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _batch():
    """Batch mode so SQLite (tests) recreates the table; Postgres runs plain ALTERs."""
    sqlite = op.get_bind().dialect.name == "sqlite"
    return op.batch_alter_table(TABLE, recreate="always" if sqlite else "auto")


def upgrade():
    existing = _existing_columns()
    missing = [c for c in _columns() if c.name not in existing]
    if not missing:
        return
    with _batch() as batch_op:
        for column in missing:
            batch_op.add_column(column)


def downgrade():
    existing = _existing_columns()
    present = [c.name for c in _columns() if c.name in existing]
    if not present:
        return
    with _batch() as batch_op:
        for name in present:
            batch_op.drop_column(name)
