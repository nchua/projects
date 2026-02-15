"""
Scan Balance API endpoints
Manages scan credits for screenshot scanner monetization
"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.scan_balance import ScanBalance, PurchaseRecord
from app.schemas.scan_balance import (
    ScanBalanceResponse,
    PurchaseVerifyRequest,
    PurchaseVerifyResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Product ID to credits mapping
PRODUCT_CREDITS = {
    "com.nickchua.fitnessapp.scan_20": 20,
    "com.nickchua.fitnessapp.scan_50": 50,
    "com.nickchua.fitnessapp.scan_unlimited": 0,  # Unlimited, no credits added
}

UNLIMITED_PRODUCT_ID = "com.nickchua.fitnessapp.scan_unlimited"


def _get_or_create_balance(db: Session, user_id: str) -> ScanBalance:
    """Get existing balance or create a new one with default free credits."""
    balance = db.query(ScanBalance).filter(ScanBalance.user_id == user_id).first()
    if not balance:
        balance = ScanBalance(
            user_id=user_id,
            scan_credits=settings.FREE_MONTHLY_SCANS,
            has_unlimited=False,
            free_scans_reset_at=datetime.utcnow() + timedelta(days=30),
        )
        db.add(balance)
        db.commit()
        db.refresh(balance)
    return balance


def _check_monthly_reset(db: Session, balance: ScanBalance) -> ScanBalance:
    """If the free scans reset period has passed, add free credits and advance reset date."""
    now = datetime.utcnow()
    if balance.free_scans_reset_at and now >= balance.free_scans_reset_at:
        balance.scan_credits += settings.FREE_MONTHLY_SCANS
        # Advance reset date by 30 days from the previous reset (not from now)
        while balance.free_scans_reset_at <= now:
            balance.free_scans_reset_at += timedelta(days=30)
        db.commit()
        db.refresh(balance)
    return balance


@router.get("", response_model=ScanBalanceResponse)
@router.get("/", response_model=ScanBalanceResponse)
async def get_scan_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScanBalanceResponse:
    """Get current scan balance. Lazy-creates row for new users and applies monthly free reset."""
    balance = _get_or_create_balance(db, current_user.id)
    balance = _check_monthly_reset(db, balance)
    return ScanBalanceResponse(
        scan_credits=balance.scan_credits,
        has_unlimited=balance.has_unlimited,
        free_scans_reset_at=balance.free_scans_reset_at,
    )


@router.post("/verify-purchase", response_model=PurchaseVerifyResponse)
@router.post("/verify-purchase/", response_model=PurchaseVerifyResponse)
async def verify_purchase(
    request: PurchaseVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PurchaseVerifyResponse:
    """
    Verify an App Store purchase and credit the user's scan balance.

    - Validates transaction_id uniqueness (prevents double-crediting)
    - Maps product_id to credits
    - Updates balance
    """
    # Check for duplicate transaction
    existing = db.query(PurchaseRecord).filter(
        PurchaseRecord.transaction_id == request.transaction_id
    ).first()
    if existing:
        # Already processed — return current balance without error
        balance = _get_or_create_balance(db, current_user.id)
        logger.info(f"Duplicate transaction {request.transaction_id} for user {current_user.id}")
        return PurchaseVerifyResponse(
            success=True,
            credits_added=0,
            new_balance=balance.scan_credits,
            has_unlimited=balance.has_unlimited,
        )

    # Validate product_id
    if request.product_id not in PRODUCT_CREDITS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown product_id: {request.product_id}",
        )

    balance = _get_or_create_balance(db, current_user.id)
    credits_to_add = PRODUCT_CREDITS[request.product_id]
    is_unlimited = request.product_id == UNLIMITED_PRODUCT_ID

    # Update balance
    if is_unlimited:
        balance.has_unlimited = True
        purchase_type = "non_consumable"
    else:
        balance.scan_credits += credits_to_add
        purchase_type = "consumable"

    # Record purchase
    record = PurchaseRecord(
        user_id=current_user.id,
        product_id=request.product_id,
        transaction_id=request.transaction_id,
        credits_added=credits_to_add,
        purchase_type=purchase_type,
    )
    db.add(record)
    db.commit()
    db.refresh(balance)

    logger.info(
        f"Purchase verified: user={current_user.id}, product={request.product_id}, "
        f"credits_added={credits_to_add}, unlimited={is_unlimited}"
    )

    return PurchaseVerifyResponse(
        success=True,
        credits_added=credits_to_add,
        new_balance=balance.scan_credits,
        has_unlimited=balance.has_unlimited,
    )


@router.post("/restore-purchases", response_model=ScanBalanceResponse)
@router.post("/restore-purchases/", response_model=ScanBalanceResponse)
async def restore_purchases(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScanBalanceResponse:
    """
    Restore non-consumable purchases (S-Rank unlimited scanner).

    Called when the user taps "Restore Purchases" in the paywall.
    Checks if user has any existing unlimited purchase records.
    """
    balance = _get_or_create_balance(db, current_user.id)

    # Check if user has an unlimited purchase record
    unlimited_purchase = db.query(PurchaseRecord).filter(
        PurchaseRecord.user_id == current_user.id,
        PurchaseRecord.product_id == UNLIMITED_PRODUCT_ID,
    ).first()

    if unlimited_purchase and not balance.has_unlimited:
        balance.has_unlimited = True
        db.commit()
        db.refresh(balance)
        logger.info(f"Restored unlimited purchase for user {current_user.id}")

    balance = _check_monthly_reset(db, balance)
    return ScanBalanceResponse(
        scan_credits=balance.scan_credits,
        has_unlimited=balance.has_unlimited,
        free_scans_reset_at=balance.free_scans_reset_at,
    )
