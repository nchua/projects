"""Owner console / control plane — seed products, backfill unlimited rows (spec §12)

Inserts the catalog from ``entitlement_service.DEFAULT_PRODUCTS`` (the three
App Store products the code used to hardcode), insert-if-missing, and gives every user whose
``scan_balances.has_unlimited`` is already true an active ``scans.unlimited``
entitlement row (``source = purchase`` when an unlimited receipt exists,
else ``backfill``) so the owner's script-granted flag is represented on day
one and the fleet drift list starts empty.

Data-only; never deletes user data on downgrade (no-op). Re-runs are no-ops.

Revision ID: admin_seed_backfill
Revises: admin_schema
Create Date: 2026-09-05

"""
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op
from app.services.entitlement_service import (
    DEFAULT_PRODUCTS,
    KEY_UNLIMITED,
    UNLIMITED_PRODUCT_ID,
)

# revision identifiers, used by Alembic.
revision = "admin_seed_backfill"
down_revision = "admin_schema"
branch_labels = None
depends_on = None

products = sa.table(
    "products",
    sa.column("id", sa.String),
    sa.column("kind", sa.String),
    sa.column("credits", sa.Integer),
    sa.column("entitlement_key", sa.String),
    sa.column("display_name", sa.String),
    sa.column("active", sa.Boolean),
    sa.column("sort_order", sa.Integer),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)

entitlements = sa.table(
    "user_entitlements",
    sa.column("id", sa.String),
    sa.column("user_id", sa.String),
    sa.column("key", sa.String),
    sa.column("value", sa.JSON),
    sa.column("source", sa.String),
    sa.column("purchase_record_id", sa.String),
    sa.column("reason", sa.String),
    sa.column("created_at", sa.DateTime),
)


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _seed_products(conn) -> int:
    existing = {r[0] for r in conn.execute(sa.text("SELECT id FROM products"))}
    now = datetime.now(timezone.utc)
    added = 0
    for spec in DEFAULT_PRODUCTS:
        if spec["id"] in existing:
            continue
        conn.execute(
            products.insert().values(active=True, created_at=now, updated_at=now, **spec)
        )
        added += 1
    return added


def _backfill_unlimited(conn) -> int:
    rows = conn.execute(
        sa.text(
            "SELECT b.user_id FROM scan_balances b "
            "WHERE b.has_unlimited = :yes AND NOT EXISTS ("
            "  SELECT 1 FROM user_entitlements e "
            "  WHERE e.user_id = b.user_id AND e.key = :key AND e.revoked_at IS NULL)"
        ),
        {"yes": True, "key": KEY_UNLIMITED},
    ).fetchall()
    now = datetime.now(timezone.utc)
    inserted = 0
    for (user_id,) in rows:
        receipt = conn.execute(
            sa.text(
                "SELECT id FROM purchase_records "
                "WHERE user_id = :u AND product_id = :p ORDER BY created_at LIMIT 1"
            ),
            {"u": user_id, "p": UNLIMITED_PRODUCT_ID},
        ).fetchone()
        conn.execute(
            entitlements.insert().values(
                id=str(uuid.uuid4()),
                user_id=user_id,
                key=KEY_UNLIMITED,
                value=True,
                source="purchase" if receipt else "backfill",
                purchase_record_id=receipt[0] if receipt else None,
                reason="migration backfill of scan_balances.has_unlimited",
                created_at=now,
            )
        )
        inserted += 1
    return inserted


def upgrade():
    if not (_has_table("products") and _has_table("user_entitlements")):
        return
    conn = op.get_bind()
    _seed_products(conn)
    if _has_table("scan_balances"):
        _backfill_unlimited(conn)


def downgrade():
    # Data-only revision: never delete user data on downgrade.
    pass
