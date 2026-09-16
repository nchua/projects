"""Index ``admin_audit_log.request_id`` (console v2 spec §7.4 v2.4)

The console groups a bulk batch by ``request_id`` (the toast's audit link and
the Audit table's Request column both filter on it), and the audit table is
append-only and only grows. One composite index, newest-first within a request.

Idempotent: inspector-guarded. No data changes.

Revision ID: audit_request_id
Revises: console_v2
Create Date: 2026-09-15

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "audit_request_id"
down_revision = "console_v2"
branch_labels = None
depends_on = None

TABLE = "admin_audit_log"
INDEX = "ix_admin_audit_request_id"


def _index_names() -> set:
    return {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes(TABLE)}


def upgrade():
    if INDEX not in _index_names():
        op.create_index(INDEX, TABLE, ["request_id", "created_at"])


def downgrade():
    if INDEX in _index_names():
        op.drop_index(INDEX, table_name=TABLE)
