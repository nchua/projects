"""
Entitlements and the product catalog (control-plane spec §6).

``products`` replaces the hardcoded ``PRODUCT_CREDITS`` dict: it maps an App
Store product id to its effect (credits for consumables, an entitlement key
for the unlimited SKU). Prices live in App Store Connect. Rows are never
deleted — ``purchase_records.product_id`` references them by string — only
deactivated.

``user_entitlements`` is the per-user override layer. Credits stay a balance
on ``scan_balances`` (a ledger quantity, not a right); ``has_unlimited`` on
that table stays the one boolean the scanner reads, kept in sync by
``entitlement_service.sync_unlimited_flag``. Multiple rows per key are
history; the newest active row wins.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProductKind(str, enum.Enum):
    """How a product is consumed."""

    CONSUMABLE = "consumable"
    NON_CONSUMABLE = "non_consumable"
    SUBSCRIPTION = "subscription"


class EntitlementSource(str, enum.Enum):
    """Where an entitlement row came from."""

    PURCHASE = "purchase"
    ADMIN_GRANT = "admin_grant"
    BACKFILL = "backfill"


class Product(Base):
    """Catalog SKU → effect. ``id`` is the App Store product id and is immutable."""

    __tablename__ = "products"

    id = Column(String, primary_key=True)
    kind = Column(String, nullable=False)  # ProductKind value
    credits = Column(Integer, nullable=False, default=0, server_default="0")
    entitlement_key = Column(String, nullable=True)
    display_name = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, default=True, server_default="true")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


class UserEntitlement(Base):
    """A keyed right or limit for one user, with provenance."""

    __tablename__ = "user_entitlements"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # No cascade on purpose: purge deletes these explicitly (spec §8.2).
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String, nullable=False)
    value = Column(JSON, nullable=False)
    source = Column(String, nullable=False)  # EntitlementSource value
    granted_by = Column(String, nullable=True)  # admin user id
    # Not an FK: a revoked purchase-sourced row must keep pointing at the
    # receipt even after purge unlinks the receipt from the user.
    purchase_record_id = Column(String, nullable=True, index=True)
    reason = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (Index("ix_user_entitlements_user_key", "user_id", "key"),)
