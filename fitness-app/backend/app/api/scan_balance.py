"""
Scan Balance API endpoints
Manages scan credits for screenshot scanner monetization.

Products come from the ``products`` table (control-plane spec §6.4) and the
unlimited SKU is an entitlement (§6.3); ``scan_balances.has_unlimited`` is a
cached flag whose only writer is ``entitlement_service.sync_unlimited_flag``.

``verify-purchase`` verifies the StoreKit 2 ``signed_transaction`` (JWS,
``app/core/app_store_jws.py``) when the client sends one and binds it to the
request, the app, the environment allow-list and the account. The rollout is
two-phase behind ``PURCHASE_REQUIRE_JWS``: phones built before the iOS change
send no JWS, so until the flag flips an absent JWS is accepted and the row is
recorded ``verified = false``. The §6.5 interim caps stay in force either way:
numeric ids only, a daily verification count, a daily credit cap, one
unlimited grant per account, and an owner alert on every unlimited grant.
The caps are evaluated under the balance row lock.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Set

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.app_store_jws import (
    InvalidSignedTransaction,
    SignedTransaction,
    verify_signed_transaction,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.entitlement import Product
from app.models.scan_balance import PurchaseRecord, ScanBalance
from app.models.user import User
from app.schemas.scan_balance import (
    PurchaseVerifyRequest,
    PurchaseVerifyResponse,
    ScanBalanceResponse,
)
from app.services import entitlement_service
from app.services.email_service import send_owner_alert

logger = logging.getLogger(__name__)

router = APIRouter()


def _balance_response(balance: ScanBalance) -> ScanBalanceResponse:
    return ScanBalanceResponse(
        scan_credits=balance.scan_credits,
        has_unlimited=balance.has_unlimited,
        free_scans_reset_at=balance.free_scans_reset_at,
    )


def _purchase_response(balance: ScanBalance, credits_added: int) -> PurchaseVerifyResponse:
    return PurchaseVerifyResponse(
        success=True,
        credits_added=credits_added,
        new_balance=balance.scan_credits,
        has_unlimited=balance.has_unlimited,
    )


def _current_balance(db: Session, user_id: str) -> ScanBalanceResponse:
    """Balance after lazy-create and the monthly free reset (commits if it fired)."""
    limits = entitlement_service.effective_limits(db, user_id)
    balance = entitlement_service.get_or_create_balance(
        db, user_id, free_monthly=limits.free_monthly
    )
    if entitlement_service.apply_monthly_reset(balance, limits.free_monthly):
        db.commit()
        db.refresh(balance)
    return _balance_response(balance)


@router.get("", response_model=ScanBalanceResponse)
@router.get("/", response_model=ScanBalanceResponse)
async def get_scan_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScanBalanceResponse:
    """Get current scan balance. Lazy-creates row for new users and applies monthly free reset."""
    return _current_balance(db, current_user.id)


def _enforce_purchase_caps(db: Session, user_id: str, product: Product) -> None:
    """Interim abuse caps on unverified purchases (spec §6.5). Call under the balance lock."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    verifications, credits_today = (
        db.query(
            func.count(PurchaseRecord.id),
            func.coalesce(func.sum(PurchaseRecord.credits_added), 0),
        )
        .filter(PurchaseRecord.user_id == user_id, PurchaseRecord.created_at >= since)
        .one()
    )
    if verifications >= settings.PURCHASE_MAX_VERIFICATIONS_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many purchase verifications today. Please try again tomorrow.",
            headers={"Retry-After": str(24 * 3600)},
        )
    if product.entitlement_key:
        already = (
            db.query(PurchaseRecord.id)
            .filter(PurchaseRecord.user_id == user_id, PurchaseRecord.product_id == product.id)
            .first()
        )
        if already:
            logger.warning(
                "second unlimited purchase attempt blocked: user=%s product=%s",
                user_id, product.id,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This account already holds the unlimited scanner. Use Restore Purchases.",
            )
        return
    if credits_today + product.credits > settings.PURCHASE_MAX_CREDITS_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Daily scan-credit purchase cap reached. Please try again tomorrow.",
        )


SIGNED_TRANSACTION_REJECTED = "signed_transaction could not be verified for this purchase"


def _allowed_environments() -> Set[str]:
    return {e.strip() for e in settings.PURCHASE_ALLOWED_ENVIRONMENTS.split(",") if e.strip()}


def _reject_signed(reason: str, request: PurchaseVerifyRequest, user: User) -> HTTPException:
    """422 with one non-revealing detail; the reason and ids go to the log only."""
    logger.warning(
        "signed_transaction rejected: reason=%s transaction=%s user=…%s",
        reason, request.transaction_id, user.id[-4:],
    )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=SIGNED_TRANSACTION_REJECTED
    )


def _verified_transaction(
    request: PurchaseVerifyRequest, user: User
) -> Optional[SignedTransaction]:
    """Verify ``request.signed_transaction`` and bind it to this request (spec §6.5).

    Returns the payload, or None when no JWS was sent and
    ``PURCHASE_REQUIRE_JWS`` is off (phase 1: record the row unverified).
    Every failure is a 422 whose detail never says which check failed.
    """
    jws = request.signed_transaction
    if not jws:
        if settings.PURCHASE_REQUIRE_JWS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="signed_transaction required",
            )
        return None
    try:
        payload = verify_signed_transaction(jws)
    except InvalidSignedTransaction as exc:
        raise _reject_signed(exc.reason, request, user) from None

    checks = (
        ("transaction mismatch", payload.transaction_id == request.transaction_id),
        ("product mismatch", payload.product_id == request.product_id),
        ("bundle mismatch", payload.bundle_id == settings.APP_STORE_BUNDLE_ID),
        ("environment not allowed", payload.environment in _allowed_environments()),
        ("revoked", not payload.revoked),
        (
            "appAccountToken mismatch",
            payload.app_account_token is None or payload.app_account_token == user.id.lower(),
        ),
    )
    for reason, ok in checks:
        if not ok:
            raise _reject_signed(reason, request, user)
    return payload


@router.post("/verify-purchase", response_model=PurchaseVerifyResponse)
@router.post("/verify-purchase/", response_model=PurchaseVerifyResponse)
async def verify_purchase(
    request: PurchaseVerifyRequest,
    background: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PurchaseVerifyResponse:
    """
    Verify an App Store purchase and credit the user's scan balance.

    - Validates transaction_id uniqueness (prevents double-crediting)
    - Verifies the StoreKit 2 JWS when present (required once
      ``PURCHASE_REQUIRE_JWS`` is on) and binds it to the request
    - Maps product_id to its effect through the ``products`` table
    - Grants the unlimited entitlement or adds credits, under the balance row lock
    """
    # Check for duplicate transaction
    existing = db.query(PurchaseRecord).filter(
        PurchaseRecord.transaction_id == request.transaction_id
    ).first()
    if existing:
        # Already processed — return current balance without error
        logger.info(f"Duplicate transaction {request.transaction_id} for user {current_user.id}")
        return _purchase_response(
            entitlement_service.get_or_create_balance(db, current_user.id), credits_added=0
        )

    # StoreKit 2 transaction ids are UInt64; anything else is not from the App Store.
    if not request.transaction_id.isdigit():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="transaction_id must be a numeric StoreKit transaction id",
        )

    signed = _verified_transaction(request, current_user)

    product = entitlement_service.get_product(db, request.product_id)
    if product is None or not product.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown product_id: {request.product_id}",
        )

    # Lock the balance row FIRST so the caps are evaluated serially per user:
    # N concurrent calls with distinct fabricated ids would otherwise all see
    # zero prior purchases (spec §6.5 / §11).
    balance = entitlement_service.get_or_create_balance(db, current_user.id, for_update=True)
    try:
        _enforce_purchase_caps(db, current_user.id, product)
    except HTTPException:
        db.rollback()
        raise

    is_unlimited = bool(product.entitlement_key)
    credits_to_add = 0 if is_unlimited else int(product.credits)

    record = PurchaseRecord(
        user_id=current_user.id,
        product_id=product.id,
        transaction_id=request.transaction_id,
        credits_added=credits_to_add,
        purchase_type=entitlement_service.purchase_type_for(product),
        verified=signed is not None,
        environment=signed.environment if signed else None,
        original_transaction_id=signed.original_transaction_id if signed else None,
        purchase_date=signed.purchase_date if signed else None,
    )
    db.add(record)
    db.flush()

    if is_unlimited:
        entitlement_service.grant_from_purchase(
            db, user_id=current_user.id, purchase_record_id=record.id, product=product
        )
    else:
        balance.scan_credits += credits_to_add
    db.commit()
    db.refresh(balance)

    provenance = f"verified ({signed.environment})" if signed else "unverified client claim"
    logger.info(
        f"Purchase recorded: user={current_user.id}, product={product.id}, "
        f"credits_added={credits_to_add}, unlimited={is_unlimited}, {provenance}"
    )
    if is_unlimited:
        # Off the event loop: SendGrid is a blocking HTTP call.
        background.add_task(
            send_owner_alert,
            "Unlimited scanner granted by purchase",
            f"user …{current_user.id[-4:]} product {product.id} "
            f"transaction {request.transaction_id} ({provenance})",
        )

    return _purchase_response(balance, credits_to_add)


@router.post("/restore-purchases", response_model=ScanBalanceResponse)
@router.post("/restore-purchases/", response_model=ScanBalanceResponse)
async def restore_purchases(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScanBalanceResponse:
    """
    Restore non-consumable purchases (S-Rank unlimited scanner).

    Re-derives the unlimited entitlement from the user's purchase records. A
    grant is a no-op for any receipt an entitlement row already references —
    active or revoked — so an admin revoke survives a restore (spec §6.3).
    """
    receipts = (
        db.query(PurchaseRecord, Product)
        .join(Product, Product.id == PurchaseRecord.product_id)
        .filter(PurchaseRecord.user_id == current_user.id, Product.entitlement_key.isnot(None))
        .all()
    )
    for record, product in receipts:
        entitlement_service.grant_from_purchase(
            db, user_id=current_user.id, purchase_record_id=record.id, product=product
        )
    derived = entitlement_service.sync_unlimited_flag(db, current_user.id)
    db.commit()
    if derived:
        logger.info(f"Restored unlimited purchase for user {current_user.id}")
    return _current_balance(db, current_user.id)
