"""Owner console / control plane — admin schema (spec §12)

users gain is_admin, token_version, admin_failed_logins, admin_locked_until.
purchase_records.user_id becomes nullable (hard purge unlinks receipts
instead of deleting them, §8.2). New tables: admin_audit_log (+ a Postgres
BEFORE UPDATE OR DELETE trigger so it is append-only), products,
user_entitlements.

Idempotent: every create/add/alter is inspector-guarded, so a re-run on an
already-migrated schema is a no-op. Plain ADD COLUMN works on SQLite and
Postgres alike; only the nullability change uses batch mode.

Revision ID: admin_schema
Revises: v3_drop_quest_tables
Create Date: 2026-09-05

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "admin_schema"
down_revision = "v3_drop_quest_tables"
branch_labels = None
depends_on = None

TRIGGER_FN = "admin_audit_log_append_only"
TRIGGER = "trg_admin_audit_log_append_only"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _columns(table: str) -> dict:
    return {c["name"]: c for c in _inspector().get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {ix["name"] for ix in _inspector().get_indexes(table)}


def _dialect() -> str:
    return op.get_bind().dialect.name


def _batch_kwargs() -> dict:
    return {"recreate": "always"} if _dialect() == "sqlite" else {}


def _add_users_columns() -> None:
    cols = _columns("users")
    for column in (
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("admin_failed_logins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("admin_locked_until", sa.DateTime(), nullable=True),
    ):
        if column.name not in cols:
            op.add_column("users", column)


def _relax_purchase_user_fk() -> None:
    if not _has_table("purchase_records"):
        return
    col = _columns("purchase_records").get("user_id")
    if col is None or col.get("nullable"):
        return
    with op.batch_alter_table("purchase_records", **_batch_kwargs()) as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.String(), nullable=True)


def _create_audit_log() -> None:
    if not _has_table("admin_audit_log"):
        op.create_table(
            "admin_audit_log",
            sa.Column("id", sa.String(), primary_key=True),
            # Plain string on purpose: a FK with SET NULL would fire the
            # append-only trigger during a user purge.
            sa.Column("actor_user_id", sa.String(), nullable=True),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("target_type", sa.String(), nullable=False),
            sa.Column("target_id", sa.String(), nullable=True),
            sa.Column("before", sa.JSON(), nullable=True),
            sa.Column("after", sa.JSON(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("request_id", sa.String(), nullable=True),
            sa.Column("ip", sa.String(), nullable=True),
            sa.Column("idempotency_key", sa.String(), nullable=True),
            sa.Column("body_sha256", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    partial = sa.text("idempotency_key IS NOT NULL")
    for name, cols, kwargs in (
        ("ix_admin_audit_log_action", ["action"], {}),
        ("ix_admin_audit_target", ["target_type", "target_id", "created_at"], {}),
        ("ix_admin_audit_actor", ["actor_user_id", "created_at"], {}),
        (
            "uq_admin_audit_idempotency",
            ["actor_user_id", "idempotency_key"],
            {"unique": True, "postgresql_where": partial, "sqlite_where": partial},
        ),
    ):
        if not _has_index("admin_audit_log", name):
            op.create_index(name, "admin_audit_log", cols, **kwargs)
    if _dialect() == "postgresql":
        op.execute(
            f"CREATE OR REPLACE FUNCTION {TRIGGER_FN}() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'admin_audit_log is append-only'; END; "
            "$$ LANGUAGE plpgsql;"
        )
        op.execute(f"DROP TRIGGER IF EXISTS {TRIGGER} ON admin_audit_log;")
        op.execute(
            f"CREATE TRIGGER {TRIGGER} BEFORE UPDATE OR DELETE ON admin_audit_log "
            f"FOR EACH ROW EXECUTE FUNCTION {TRIGGER_FN}();"
        )


def _create_products() -> None:
    if not _has_table("products"):
        op.create_table(
            "products",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("credits", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("entitlement_key", sa.String(), nullable=True),
            sa.Column("display_name", sa.String(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def _create_entitlements() -> None:
    if not _has_table("user_entitlements"):
        op.create_table(
            "user_entitlements",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("value", sa.JSON(), nullable=False),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("granted_by", sa.String(), nullable=True),
            sa.Column("purchase_record_id", sa.String(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    for name, cols in (
        ("ix_user_entitlements_user_id", ["user_id"]),
        ("ix_user_entitlements_purchase_record_id", ["purchase_record_id"]),
        ("ix_user_entitlements_user_key", ["user_id", "key"]),
    ):
        if not _has_index("user_entitlements", name):
            op.create_index(name, "user_entitlements", cols)


def upgrade():
    _add_users_columns()
    _relax_purchase_user_fk()
    _create_audit_log()
    _create_products()
    _create_entitlements()


def downgrade():
    if _dialect() == "postgresql":
        op.execute(f"DROP TRIGGER IF EXISTS {TRIGGER} ON admin_audit_log;")
        op.execute(f"DROP FUNCTION IF EXISTS {TRIGGER_FN}();")
    for table in ("user_entitlements", "products", "admin_audit_log"):
        if _has_table(table):
            op.drop_table(table)
    # purchase_records.user_id stays nullable on downgrade: tightening it
    # would fail if any receipt has been unlinked by a purge.
    cols = _columns("users")
    present = [
        c
        for c in ("admin_locked_until", "admin_failed_logins", "token_version", "is_admin")
        if c in cols
    ]
    if present:
        with op.batch_alter_table("users", **_batch_kwargs()) as batch_op:
            for c in present:
                batch_op.drop_column(c)
