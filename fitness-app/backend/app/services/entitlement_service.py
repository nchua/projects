"""
Entitlements, per-user scan limits, and the product catalog
(control-plane spec §6).

Resolution: newest active per-user row → global default via
``settings_service`` (``app_settings`` row → ``Settings`` env / code).
``scan_balances.has_unlimited`` stays the one boolean the scanner reads under
its row lock; :func:`sync_unlimited_flag` is its only writer and runs inside
the caller's transaction holding that lock.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.utils import ensure_utc, to_naive_utc
from app.models.entitlement import EntitlementSource, Product, ProductKind, UserEntitlement
from app.models.scan_balance import ScanBalance
from app.services import settings_service

KEY_UNLIMITED = "scans.unlimited"
KEY_DAILY_LIMIT = "scans.daily_limit"
KEY_COOLDOWN = "scans.cooldown_seconds"
KEY_FREE_MONTHLY = "scans.free_monthly"

# key → expected value type. Grants validate against this registry.
ENTITLEMENT_KEYS: Dict[str, type] = {
    KEY_UNLIMITED: bool,
    KEY_DAILY_LIMIT: int,
    KEY_COOLDOWN: int,
    KEY_FREE_MONTHLY: int,
}

UNLIMITED_PRODUCT_ID = "com.nickchua.fitnessapp.scan_unlimited"

# Seed catalog; alembic/versions/admin_seed_backfill.py imports and inserts it if missing.
DEFAULT_PRODUCTS: List[Dict[str, Any]] = [
    {
        "id": "com.nickchua.fitnessapp.scan_20",
        "kind": ProductKind.CONSUMABLE.value,
        "credits": 20,
        "entitlement_key": None,
        "display_name": "Quick — 20 scans",
        "sort_order": 0,
    },
    {
        "id": "com.nickchua.fitnessapp.scan_50",
        "kind": ProductKind.CONSUMABLE.value,
        "credits": 50,
        "entitlement_key": None,
        "display_name": "Power — 50 scans",
        "sort_order": 1,
    },
    {
        "id": UNLIMITED_PRODUCT_ID,
        "kind": ProductKind.NON_CONSUMABLE.value,
        "credits": 0,
        "entitlement_key": KEY_UNLIMITED,
        "display_name": "S-Rank — unlimited scans",
        "sort_order": 2,
    },
]


@dataclass(frozen=True)
class ScanLimits:
    """Effective scanner limits for one user."""

    daily_limit: int
    cooldown_seconds: int
    free_monthly: int


def default_scan_limits(db: Session) -> ScanLimits:
    """Global defaults through the resolver (console row → ``settings`` at call time)."""
    return ScanLimits(
        daily_limit=int(settings_service.get(db, "DAILY_SCREENSHOT_LIMIT")),
        cooldown_seconds=int(settings_service.get(db, "COOLDOWN_SECONDS")),
        free_monthly=int(settings_service.get(db, "FREE_MONTHLY_SCANS")),
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def validate_grant(key: str, value: Any) -> None:
    """Raise ``ValueError`` for an unknown key or a value of the wrong type."""
    expected = ENTITLEMENT_KEYS.get(key)
    if expected is None:
        raise ValueError(f"Unknown entitlement key: {key}")
    if expected is bool:
        if not isinstance(value, bool):
            raise ValueError(f"{key} expects a boolean")
    elif expected is int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{key} expects a non-negative integer")


def is_active(row: UserEntitlement, now: datetime) -> bool:
    """True when ``row`` is unrevoked and unexpired at ``now`` (the §6.1 active rule)."""
    if row.revoked_at is not None:
        return False
    expires = ensure_utc(row.expires_at)
    return expires is None or expires > now


def active_clauses(now: datetime) -> Tuple[ColumnElement, ...]:
    """SQL twin of :func:`is_active` — for the admin list's correlated subqueries.

    Compares ``expires_at`` against a naive UTC ``now`` (SQLite stores naive
    datetimes); Python-side readers keep using :func:`is_active`.
    """
    return (
        UserEntitlement.revoked_at.is_(None),
        or_(UserEntitlement.expires_at.is_(None), UserEntitlement.expires_at > to_naive_utc(now)),
    )


def active_entitlements(db: Session, user_id: str, keys: Iterable[str]) -> List[UserEntitlement]:
    """Active rows for ``user_id`` among ``keys``, newest first.

    Expiry is evaluated in Python via ``ensure_utc``: SQLite stores naive
    datetimes, so a SQL comparison against an aware ``now`` is unreliable.
    """
    now = _utcnow()
    rows = (
        db.query(UserEntitlement)
        .filter(
            UserEntitlement.user_id == user_id,
            UserEntitlement.key.in_(list(keys)),
            UserEntitlement.revoked_at.is_(None),
        )
        .order_by(UserEntitlement.created_at.desc(), UserEntitlement.id.desc())
        .all()
    )
    return [row for row in rows if is_active(row, now)]


def list_entitlements(db: Session, user_id: str) -> List[UserEntitlement]:
    """Every row (history included), newest first."""
    return (
        db.query(UserEntitlement)
        .filter(UserEntitlement.user_id == user_id)
        .order_by(UserEntitlement.created_at.desc(), UserEntitlement.id.desc())
        .all()
    )


def resolve(db: Session, user_id: str, key: str) -> Optional[Any]:
    """Value of the newest active row for ``key``, or None."""
    rows = active_entitlements(db, user_id, [key])
    return rows[0].value if rows else None


def is_entitled(db: Session, user_id: str, key: str) -> bool:
    """True when the newest active row for ``key`` holds a truthy value."""
    return bool(resolve(db, user_id, key))


def effective_limits(db: Session, user_id: str, *, base: Optional[ScanLimits] = None) -> ScanLimits:
    """Per-user overrides overlaid on the global defaults (one indexed query; pass ``base`` to reuse them)."""
    base = base or default_scan_limits(db)
    values: Dict[str, Any] = {}
    for row in active_entitlements(db, user_id, [KEY_DAILY_LIMIT, KEY_COOLDOWN, KEY_FREE_MONTHLY]):
        values.setdefault(row.key, row.value)
    return ScanLimits(
        daily_limit=int(values.get(KEY_DAILY_LIMIT, base.daily_limit)),
        cooldown_seconds=int(values.get(KEY_COOLDOWN, base.cooldown_seconds)),
        free_monthly=int(values.get(KEY_FREE_MONTHLY, base.free_monthly)),
    )


# ── the plan model (console v2 spec §3, §6.1) ────────────────────────────────

PLAN_UNLIMITED = "unlimited"
PLAN_OVERRIDE = "override"
PLAN_CREDITS = "credits"
PLAN_FREE = "free"
# Display / sort order of the four plans (``sort=plan`` ascending).
PLAN_ORDER: Tuple[str, ...] = (PLAN_UNLIMITED, PLAN_OVERRIDE, PLAN_CREDITS, PLAN_FREE)
# The keys whose active row makes a hunter "Override" (§3.1), in display order.
OVERRIDE_KEYS: Tuple[str, ...] = (KEY_FREE_MONTHLY, KEY_DAILY_LIMIT, KEY_COOLDOWN)
PLAN_KEYS: Tuple[str, ...] = (KEY_UNLIMITED,) + OVERRIDE_KEYS


@dataclass(frozen=True)
class Plan:
    """The derived plan of one hunter — the single definition every surface uses (§3)."""

    plan: str                              # unlimited | override | credits | free
    plan_source: Optional[str]             # unlimited only: purchase | admin_grant | backfill
    expires_at: Optional[datetime]         # unlimited only: the active row's expiry
    scan_credits: Optional[int]            # None when no balance row exists yet
    purchased_credits: int                 # max(0, credits - effective free_monthly)
    free_monthly: int                      # effective (override-aware) free grant
    override_keys: Tuple[str, ...]         # active override keys, even under Unlimited


def plan_snapshot(plan: Plan) -> Dict[str, Any]:
    """JSON-safe dict of a ``Plan`` for audit ``before`` / ``after`` and responses."""
    data = asdict(plan)
    data["override_keys"] = list(plan.override_keys)
    return data


def unlimited_source(row: UserEntitlement) -> str:
    """``purchase`` when the row cites a receipt, else the row's own source (§3.1)."""
    return EntitlementSource.PURCHASE.value if row.purchase_record_id else str(row.source)


def _newest_active_by_key(rows: Iterable[UserEntitlement], now: datetime) -> Dict[str, UserEntitlement]:
    """``rows`` newest-first → the newest active row per key (the §6.1 rule)."""
    newest: Dict[str, UserEntitlement] = {}
    for row in rows:
        if row.key not in newest and is_active(row, now):
            newest[row.key] = row
    return newest


def _plan_from(newest: Dict[str, UserEntitlement], credits: Optional[int], default_free: int) -> Plan:
    free_row = newest.get(KEY_FREE_MONTHLY)
    free_monthly = int(free_row.value) if free_row is not None else default_free
    override_keys = tuple(k for k in OVERRIDE_KEYS if k in newest)
    purchased = max(0, int(credits or 0) - free_monthly)
    unlimited = newest.get(KEY_UNLIMITED)
    if unlimited is not None and bool(unlimited.value):
        plan, source, expires = PLAN_UNLIMITED, unlimited_source(unlimited), ensure_utc(unlimited.expires_at)
    elif override_keys:
        plan, source, expires = PLAN_OVERRIDE, None, None
    elif purchased > 0:
        plan, source, expires = PLAN_CREDITS, None, None
    else:
        plan, source, expires = PLAN_FREE, None, None
    return Plan(
        plan=plan,
        plan_source=source,
        expires_at=expires,
        scan_credits=credits,
        purchased_credits=purchased,
        free_monthly=free_monthly,
        override_keys=override_keys,
    )


def plans_for(db: Session, user_ids: Sequence[str], *, default_free: Optional[int] = None) -> Dict[str, Plan]:
    """``Plan`` for every id in three queries — entitlements, balances, the
    global free monthly (pass ``default_free`` when already resolved) — never
    one per user (§6.1). Unknown ids get the Free plan."""
    ids = list(dict.fromkeys(user_ids))
    if not ids:
        return {}
    now = _utcnow()
    if default_free is None:
        default_free = int(settings_service.get(db, "FREE_MONTHLY_SCANS"))
    rows = (
        db.query(UserEntitlement)
        .filter(
            UserEntitlement.user_id.in_(ids),
            UserEntitlement.key.in_(PLAN_KEYS),
            UserEntitlement.revoked_at.is_(None),
        )
        .order_by(UserEntitlement.created_at.desc(), UserEntitlement.id.desc())
        .all()
    )
    by_user: Dict[str, List[UserEntitlement]] = {}
    for row in rows:
        by_user.setdefault(row.user_id, []).append(row)
    credits: Dict[str, int] = dict(
        db.query(ScanBalance.user_id, ScanBalance.scan_credits).filter(ScanBalance.user_id.in_(ids)).all()
    )
    return {
        user_id: _plan_from(_newest_active_by_key(by_user.get(user_id, []), now), credits.get(user_id), default_free)
        for user_id in ids
    }


def plan_for(db: Session, user_id: str) -> Plan:
    """The derived plan of one hunter (§3.1)."""
    return plans_for(db, [user_id])[user_id]


def get_or_create_balance(
    db: Session,
    user_id: str,
    *,
    for_update: bool = False,
    free_monthly: Optional[int] = None,
    commit: bool = True,
) -> ScanBalance:
    """Return the user's balance row, creating it if missing.

    Creation seeds ``scan_credits`` with the user's effective free monthly
    scans and derives ``has_unlimited`` from entitlements. By default the
    new row is committed on its own (the request-path behaviour the scanner
    relies on); callers already inside a transaction that must stay atomic
    — ``sync_unlimited_flag`` — pass ``commit=False`` to flush only. Pass
    ``for_update=True`` to re-select the row under a ``FOR UPDATE`` lock.
    """
    query = db.query(ScanBalance).filter(ScanBalance.user_id == user_id)
    balance = (query.with_for_update() if for_update else query).first()
    if balance is None:
        if free_monthly is None:
            free_monthly = effective_limits(db, user_id).free_monthly
        balance = ScanBalance(
            user_id=user_id,
            scan_credits=int(free_monthly),
            has_unlimited=is_entitled(db, user_id, KEY_UNLIMITED),
            free_scans_reset_at=_utcnow() + timedelta(days=30),
        )
        db.add(balance)
        if commit:
            db.commit()
            db.refresh(balance)
        else:
            db.flush()
        if for_update:
            balance = query.with_for_update().first()
    return balance


def apply_monthly_reset(balance: ScanBalance, free_monthly: int) -> bool:
    """Credit the free monthly scans if the reset date has passed.

    Advances ``free_scans_reset_at`` in 30-day steps until it is in the
    future (one credit even if several periods elapsed). Mutates the row
    without committing — call it under the balance row lock so two
    concurrent requests cannot each apply the reset. Returns True if it fired.
    """
    now = _utcnow()
    reset_at = ensure_utc(balance.free_scans_reset_at)
    if reset_at is None or now < reset_at:
        return False
    balance.scan_credits += free_monthly
    next_reset = balance.free_scans_reset_at
    while ensure_utc(next_reset) <= now:
        next_reset = next_reset + timedelta(days=30)
    balance.free_scans_reset_at = next_reset
    return True


def sync_unlimited_flag(db: Session, user_id: str) -> bool:
    """Make ``scan_balances.has_unlimited`` equal the derived entitlement.

    The single writer of that column. Locks the balance row so it cannot
    race ``_reserve_scan_credits``; flushes, never commits — a missing
    balance row is created in the caller's transaction, not committed.
    """
    balance = get_or_create_balance(db, user_id, for_update=True, commit=False)
    derived = is_entitled(db, user_id, KEY_UNLIMITED)
    if bool(balance.has_unlimited) != derived:
        balance.has_unlimited = derived
    db.flush()
    return derived


def grant(
    db: Session,
    *,
    user_id: str,
    key: str,
    value: Any,
    source: Union[EntitlementSource, str],
    granted_by: Optional[str] = None,
    purchase_record_id: Optional[str] = None,
    reason: Optional[str] = None,
    expires_at: Optional[datetime] = None,
) -> Optional[UserEntitlement]:
    """Create an entitlement row (flush, no commit).

    Returns None without writing when ``purchase_record_id`` is already
    referenced by ANY row, active or revoked — this is what makes an admin
    revoke survive "Restore Purchases" (spec §6.3). Raises ``ValueError`` on
    an unknown key or a mistyped value.
    """
    validate_grant(key, value)
    source_value = EntitlementSource(source).value  # ValueError for unknown sources
    if purchase_record_id is not None:
        exists = (
            db.query(UserEntitlement.id)
            .filter(UserEntitlement.purchase_record_id == purchase_record_id)
            .first()
        )
        if exists:
            return None
    row = UserEntitlement(
        user_id=user_id,
        key=key,
        value=value,
        source=source_value,
        granted_by=granted_by,
        purchase_record_id=purchase_record_id,
        reason=reason,
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    if key == KEY_UNLIMITED:
        sync_unlimited_flag(db, user_id)
    return row


def revoke(db: Session, row: UserEntitlement) -> UserEntitlement:
    """Mark a row revoked (flush, no commit) and resync the unlimited flag."""
    if row.revoked_at is None:
        row.revoked_at = _utcnow()
        db.flush()
        if row.key == KEY_UNLIMITED:
            sync_unlimited_flag(db, row.user_id)
    return row


def grant_from_purchase(
    db: Session, *, user_id: str, purchase_record_id: str, product: Product
) -> Optional[UserEntitlement]:
    """Grant the entitlement a purchased product carries.

    None for credit packs (no ``entitlement_key``) and, per :func:`grant`,
    when the receipt is already referenced by any row — so an admin revoke
    survives "Restore Purchases".
    """
    if not product.entitlement_key:
        return None
    return grant(
        db,
        user_id=user_id,
        key=product.entitlement_key,
        value=True,
        source=EntitlementSource.PURCHASE,
        purchase_record_id=purchase_record_id,
        reason=f"purchase {product.id}",
    )


# ── product catalog ──────────────────────────────────────────────────────────

def ensure_products(db: Session) -> int:
    """Insert any missing seed products (never updates or deletes). Commits."""
    existing = {p.id for p in db.query(Product.id).all()}
    added = 0
    for spec in DEFAULT_PRODUCTS:
        if spec["id"] in existing:
            continue
        db.add(Product(active=True, **spec))
        added += 1
    if added:
        db.commit()
    return added


def get_product(db: Session, product_id: str) -> Optional[Product]:
    """Catalog row by App Store product id (active or not)."""
    return db.query(Product).filter(Product.id == product_id).first()


def purchase_type_for(product: Product) -> str:
    """``purchase_records.purchase_type`` value for a product."""
    return "consumable" if product.kind == ProductKind.CONSUMABLE.value else "non_consumable"
