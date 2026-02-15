"""
Scan balance and purchase record models for screenshot scanner paywall
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey
from datetime import datetime, timedelta
import uuid
from app.core.database import Base


class ScanBalance(Base):
    """Tracks scan credit balance per user for screenshot scanner monetization"""
    __tablename__ = "scan_balances"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    scan_credits = Column(Integer, default=3, nullable=False)
    has_unlimited = Column(Boolean, default=False, nullable=False)
    free_scans_reset_at = Column(
        DateTime,
        default=lambda: datetime.utcnow() + timedelta(days=30),
        nullable=False
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PurchaseRecord(Base):
    """Records IAP transactions to prevent double-crediting"""
    __tablename__ = "purchase_records"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(String, nullable=False)
    transaction_id = Column(String, nullable=False, unique=True)
    credits_added = Column(Integer, nullable=False, default=0)
    purchase_type = Column(String, nullable=False)  # "consumable" or "non_consumable"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
