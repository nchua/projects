"""
Pydantic schemas for scan balance and purchase verification
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ScanBalanceResponse(BaseModel):
    """Response schema for scan balance queries"""
    scan_credits: int
    has_unlimited: bool
    free_scans_reset_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PurchaseVerifyRequest(BaseModel):
    """Request schema for verifying an App Store purchase"""
    transaction_id: str
    product_id: str
    signed_transaction: Optional[str] = None  # JWS from StoreKit 2


class PurchaseVerifyResponse(BaseModel):
    """Response schema after verifying a purchase"""
    success: bool
    credits_added: int
    new_balance: int
    has_unlimited: bool
