"""
Control-plane migrations — idempotency, round-trip, seed and backfill on SQLite
(mirrors test_v3_migrations.py).
"""
import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.database import Base
from tests.helpers_migrations import (
    BACKEND,
    columns,
    downgrade_all,
    load_migration,
    schema_snapshot,
    tables,
    upgrade_all,
)

CHAIN = ["admin_schema", "admin_seed_backfill", "purchase_verification"]

NEW_TABLES = {"admin_audit_log", "products", "user_entitlements"}
NEW_COLUMNS = {
    "users": {"is_admin", "token_version", "admin_failed_logins", "admin_locked_until"},
    "purchase_records": {"verified", "environment", "original_transaction_id", "purchase_date"},
}
UNLIMITED = "com.nickchua.fitnessapp.scan_unlimited"


def _assert_present(engine):
    assert NEW_TABLES <= tables(engine)
    for table, cols in NEW_COLUMNS.items():
        assert cols <= columns(engine, table), (table, cols - columns(engine, table))


def _assert_absent(engine):
    assert not (NEW_TABLES & tables(engine))
    for table, cols in NEW_COLUMNS.items():
        assert not (cols & columns(engine, table)), (table, cols & columns(engine, table))


@pytest.fixture
def engine(tmp_path):
    eng = sa.create_engine(f"sqlite:///{tmp_path / 'admin_migrations.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_alembic_has_exactly_one_head():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == ["purchase_verification"]


def test_chain_is_linear_from_quest_drop():
    assert load_migration("admin_schema").down_revision == "v3_drop_quest_tables"
    assert load_migration("admin_seed_backfill").down_revision == "admin_schema"
    assert load_migration("purchase_verification").down_revision == "admin_seed_backfill"


def test_already_applied_schema_is_a_noop(engine):
    before = schema_snapshot(engine)
    upgrade_all(engine, CHAIN)
    assert schema_snapshot(engine) == before


def test_round_trip(engine):
    _assert_present(engine)
    downgrade_all(engine, CHAIN)
    _assert_absent(engine)
    upgrade_all(engine, CHAIN)
    _assert_present(engine)
    upgrade_all(engine, CHAIN)  # idempotent re-run
    _assert_present(engine)
    downgrade_all(engine, CHAIN)
    _assert_absent(engine)


def test_purchase_records_user_id_is_nullable_after_upgrade(engine):
    downgrade_all(engine, CHAIN)
    upgrade_all(engine, CHAIN)
    cols = {c["name"]: c for c in sa.inspect(engine).get_columns("purchase_records")}
    assert cols["user_id"]["nullable"] is True
    # JWS verification columns (§6.5): existing rows must read verified = false.
    assert cols["verified"]["nullable"] is False and cols["verified"]["default"] is not None
    assert cols["environment"]["nullable"] and cols["purchase_date"]["nullable"]


def test_pre_verification_rows_read_unverified_after_upgrade(engine):
    downgrade_all(engine, CHAIN)
    upgrade_all(engine, CHAIN[:-1])
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO purchase_records (id, product_id, transaction_id, credits_added, purchase_type, created_at) "
            "VALUES ('pr-old', 'com.nickchua.fitnessapp.scan_20', '1000000777', 20, 'consumable', :now)"
        ), {"now": datetime.now(timezone.utc)})
    upgrade_all(engine, CHAIN[-1:])
    with engine.connect() as conn:
        row = conn.execute(sa.text(
            "SELECT verified, environment, original_transaction_id, purchase_date FROM purchase_records WHERE id = 'pr-old'"
        )).one()
    assert (bool(row[0]), row[1], row[2], row[3]) == (False, None, None, None)


def test_indexes_created(engine):
    downgrade_all(engine, CHAIN)
    upgrade_all(engine, CHAIN)
    audit_ix = {ix["name"] for ix in sa.inspect(engine).get_indexes("admin_audit_log")}
    assert {"ix_admin_audit_log_action", "ix_admin_audit_target", "ix_admin_audit_actor", "uq_admin_audit_idempotency"} <= audit_ix
    ent_ix = {ix["name"] for ix in sa.inspect(engine).get_indexes("user_entitlements")}
    assert {"ix_user_entitlements_user_id", "ix_user_entitlements_purchase_record_id", "ix_user_entitlements_user_key"} <= ent_ix


def test_seed_products_and_backfill_unlimited(engine):
    downgrade_all(engine, CHAIN)
    now = datetime.now(timezone.utc)
    paid_id, granted_id, plain_id = (str(uuid.uuid4()) for _ in range(3))
    with engine.begin() as conn:
        for uid, email in ((paid_id, "paid@example.com"), (granted_id, "granted@example.com"), (plain_id, "plain@example.com")):
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, email, password_hash, is_deleted, created_at, updated_at) "
                    "VALUES (:id, :email, 'x', 0, :now, :now)"
                ),
                {"id": uid, "email": email, "now": now},
            )
        for uid, unlimited in ((paid_id, 1), (granted_id, 1), (plain_id, 0)):
            conn.execute(
                sa.text(
                    "INSERT INTO scan_balances (id, user_id, scan_credits, has_unlimited, free_scans_reset_at, created_at, updated_at) "
                    "VALUES (:id, :uid, 0, :unl, :now, :now, :now)"
                ),
                {"id": str(uuid.uuid4()), "uid": uid, "unl": unlimited, "now": now},
            )
        conn.execute(
            sa.text(
                "INSERT INTO purchase_records (id, user_id, product_id, transaction_id, credits_added, purchase_type, created_at) "
                "VALUES (:id, :uid, :pid, '900000001', 0, 'non_consumable', :now)"
            ),
            {"id": "rec-paid", "uid": paid_id, "pid": UNLIMITED, "now": now},
        )

    upgrade_all(engine, CHAIN)
    with engine.connect() as conn:
        products = conn.execute(sa.text("SELECT id, credits, entitlement_key FROM products ORDER BY sort_order")).fetchall()
        assert [p[0] for p in products] == [
            "com.nickchua.fitnessapp.scan_20", "com.nickchua.fitnessapp.scan_50", UNLIMITED,
        ]
        assert products[2][2] == "scans.unlimited"
        rows = conn.execute(
            sa.text("SELECT user_id, source, purchase_record_id FROM user_entitlements WHERE key = 'scans.unlimited'")
        ).fetchall()
    by_user = {r[0]: (r[1], r[2]) for r in rows}
    assert by_user == {paid_id: ("purchase", "rec-paid"), granted_id: ("backfill", None)}

    upgrade_all(engine, CHAIN)  # re-run: no duplicates
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM products")).scalar() == 3
        assert conn.execute(sa.text("SELECT count(*) FROM user_entitlements")).scalar() == 2
