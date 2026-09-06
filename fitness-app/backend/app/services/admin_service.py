"""
Admin service (control-plane spec §4.2 sessions, §7 support actions, §8.1
soft-delete / restore, §9 read surfaces). Every mutation takes the acting
admin, calls ``verify_step_up`` first when it is destructive-tier (§4.5),
changes rows, and writes its audit row with ``audit()`` inside the same
transaction — the route commits. Every reader composes existing services
in their read-only form and never creates rows. Hard purge lives in
``purge_service``.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import Subquery, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session
from starlette.requests import Request

from app.core.admin_auth import protect_account, verify_step_up
from app.core.config import settings
from app.core.dependencies import conflict, not_found, unauthorized, unprocessable
from app.core.security import (
    create_admin_token,
    hash_password,
    verify_password_with_rehash,
)
from app.core.utils import ensure_utc, to_naive_utc, utcnow
from app.models.admin import AdminAuditLog
from app.models.campaign import Campaign
from app.models.entitlement import EntitlementSource, Product, UserEntitlement
from app.models.exercise import Exercise
from app.models.pr import PR
from app.models.progress import UserProgress
from app.models.scan_balance import PurchaseRecord, ScanBalance
from app.models.user import User, UserProfile
from app.models.workout import WorkoutSession
from app.schemas.admin import (
    AdminBalanceBlock,
    AdminCampaignImportRequest,
    AdminCampaignSummary,
    AdminDataHealth,
    AdminEffectiveLimits,
    AdminIntegrations,
    AdminPreview,
    AdminPreviewBalance,
    AdminPreviewCondition,
    AdminPreviewHunt,
    AdminPreviewLoad,
    AdminPreviewProgress,
    AdminProfile,
    AdminPurchaseRow,
    AdminUserDetailResponse,
    AdminUserIdentity,
    AdminUserRow,
    AdminUserStateResponse,
    AdminWhoopStatus,
    ArcPreview,
    AuditEntry,
    CreditsAdjustResponse,
    EntitlementResponse,
    FamilyBackfillResponse,
    ProductResponse,
    ProductUpsertRequest,
    UnresolvedExercise,
    UserSort,
    UserUsageResponse,
)
from app.services import (
    admin_usage_service,
    campaign_service,
    campaign_templates,
    condition_service,
    entitlement_service,
    purge_service,
    training_load_service,
    xp_service,
)
from app.services.achievement_service import seed_achievement_definitions
from app.services.admin_usage_service import count_where
from app.services.audit_service import audit, body_hash, snapshot
from app.services.exercise_family_service import (
    apply_family_updates,
    ensure_families,
    planned_family_updates,
)
from app.services.training_load_service import local_day_sql


def _generic_unauthorized() -> HTTPException:
    return unauthorized("Incorrect email or password")


def mint_admin_session(
    db: Session,
    *,
    email: str,
    password: str,
    request: Optional[Request] = None,
) -> Tuple[str, datetime]:
    """Verify credentials and mint an admin token (no refresh token).

    401 (generic) for unknown/deleted user or bad password — bad passwords
    count toward the DB lockout; 423 while locked; 403 for a valid password
    on a non-admin account (does not count: ``/auth/login`` already confirms
    password validity, so there is no new oracle). Writes ``session.create``.
    """
    now = datetime.now(timezone.utc)
    user = db.query(User).filter(User.email == email).first()
    if user is None or user.is_deleted:
        raise _generic_unauthorized()

    locked_until = ensure_utc(user.admin_locked_until)
    if locked_until is not None and locked_until > now:
        retry = max(1, int((locked_until - now).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Admin login temporarily locked. Try again later.",
            headers={"Retry-After": str(retry)},
        )

    ok, needs_rehash = verify_password_with_rehash(password, user.password_hash)
    if not ok:
        user.admin_failed_logins += 1
        if user.admin_failed_logins >= settings.ADMIN_LOCKOUT_THRESHOLD:
            user.admin_locked_until = now + timedelta(minutes=settings.ADMIN_LOCKOUT_MINUTES)
            user.admin_failed_logins = 0
        db.commit()
        raise _generic_unauthorized()

    if needs_rehash:
        user.password_hash = hash_password(password)

    if not user.is_admin:
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    user.admin_failed_logins = 0
    user.admin_locked_until = None
    token, expires_at = create_admin_token(user)
    audit(
        db,
        actor=user,
        action="session.create",
        target_type="user",
        target_id=user.id,
        after={"expires_at": expires_at},
        request=request,
    )
    db.commit()
    return token, expires_at


# ── read surfaces (spec §9) ─────────────────────────────────────────────────

def _escape_like(text: str) -> str:
    """Escape LIKE metacharacters so a search for ``50%`` matches literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _sessions_rollup() -> Subquery:
    """Per-user session count + last local workout day (``local_day_sql``), as a subquery."""
    return (
        select(
            WorkoutSession.user_id.label("user_id"),
            func.count(WorkoutSession.id).label("session_count"),
            func.max(local_day_sql()).label("last_active"),
        )
        .where(WorkoutSession.deleted_at.is_(None))
        .group_by(WorkoutSession.user_id)
        .subquery()
    )


def list_users(
    db: Session,
    *,
    q: Optional[str] = None,
    deleted: Optional[bool] = None,
    unlimited: Optional[bool] = None,
    active_days: Optional[int] = None,
    sort: UserSort = "last_active",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[AdminUserRow], int]:
    """The Hunters table (spec §9.1): filters, sort, offset paging, total."""
    sessions = _sessions_rollup()
    query = (
        db.query(
            User,
            UserProgress.level,
            UserProgress.rank,
            sessions.c.session_count,
            sessions.c.last_active,
            ScanBalance.scan_credits,
            ScanBalance.has_unlimited,
        )
        .outerjoin(UserProgress, UserProgress.user_id == User.id)
        .outerjoin(sessions, sessions.c.user_id == User.id)
        .outerjoin(ScanBalance, ScanBalance.user_id == User.id)
    )
    if q:
        needle = f"%{_escape_like(q.strip())}%"
        query = query.filter(
            or_(User.email.ilike(needle, escape="\\"), User.username.ilike(needle, escape="\\"))
        )
    if deleted is not None:
        query = query.filter(User.is_deleted == deleted)
    if unlimited is not None:
        query = query.filter(func.coalesce(ScanBalance.has_unlimited, False) == unlimited)
    if active_days is not None:
        query = query.filter(sessions.c.last_active >= date.today() - timedelta(days=active_days))

    total = query.count()

    sort_column = {
        "last_active": sessions.c.last_active,
        "created": User.created_at,
        "email": User.email,
        "credits": ScanBalance.scan_credits,
    }[sort]
    primary = sort_column.desc() if order == "desc" else sort_column.asc()
    rows = query.order_by(primary.nulls_last(), User.id).offset(offset).limit(limit).all()

    return [
        AdminUserRow(
            id=user.id,
            email=user.email,
            username=user.username,
            created_at=user.created_at,
            is_deleted=bool(user.is_deleted),
            deleted_at=user.deleted_at,
            is_admin=bool(user.is_admin),
            level=level,
            rank=rank,
            last_workout_date=last_active,
            session_count=int(session_count or 0),
            scan_credits=scan_credits,
            has_unlimited=bool(has_unlimited),
        )
        for user, level, rank, session_count, last_active, scan_credits, has_unlimited in rows
    ], int(total)


def _audit_query(
    db: Session,
    *,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    action: Optional[str] = None,
) -> Query:
    query = db.query(AdminAuditLog)
    if target_type:
        query = query.filter(AdminAuditLog.target_type == target_type)
    if target_id:
        query = query.filter(AdminAuditLog.target_id == target_id)
    if actor_user_id:
        query = query.filter(AdminAuditLog.actor_user_id == actor_user_id)
    if action:
        query = query.filter(AdminAuditLog.action == action)
    return query.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())


def list_audit(
    db: Session,
    *,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[AuditEntry], int]:
    """Newest-first page of the append-only audit log (spec §5), with the total."""
    query = _audit_query(
        db, target_type=target_type, target_id=target_id, actor_user_id=actor_user_id, action=action
    )
    rows = query.offset(offset).limit(limit).all()
    return [AuditEntry.model_validate(row, from_attributes=True) for row in rows], int(query.count())


def list_products(db: Session) -> List[ProductResponse]:
    """The catalog, active or not, in display order."""
    rows = db.query(Product).order_by(Product.sort_order, Product.id).all()
    return [ProductResponse.model_validate(p, from_attributes=True) for p in rows]


def entitlement_response(row: UserEntitlement, now: Optional[datetime] = None) -> EntitlementResponse:
    """Allow-listed view of a ``user_entitlements`` row with ``active`` derived."""
    fields = {name: getattr(row, name) for name in EntitlementResponse.model_fields if name != "active"}
    return EntitlementResponse(
        active=entitlement_service.is_active(row, now or datetime.now(timezone.utc)), **fields
    )


def _campaign_summary(db: Session, campaign: Campaign, today: date) -> AdminCampaignSummary:
    payload = campaign_service.campaign_to_dict(db, campaign, today)
    upcoming = campaign_service.next_planned_hunt(db, campaign, today)
    return AdminCampaignSummary(
        **{
            **payload,
            "arcs": len(payload["arcs"]),
            "next_planned_hunt": upcoming.date.isoformat() if upcoming else None,
        }
    )


def _preview(
    db: Session,
    user: User,
    today: date,
    *,
    profile: Optional[UserProfile],
    balance: Optional[ScanBalance],
    campaign: Optional[Campaign],
    progress: Dict[str, Any],
) -> AdminPreview:
    """The Status tab as the user sees it (spec §9.2) — no impersonation token.

    Composed from the same services the app calls, in their read-only form:
    today's hunt as stored (no materialization, no fresh prescription), the
    stored load series (``read_load_state``) and the condition computed from
    it — an admin read must never advance or recompute the user's data.
    """
    hunt = campaign_service.hunt_on(db, user.id, today) if campaign is not None else None
    load = training_load_service.read_load_state(db, user.id, today)
    condition = condition_service.compute_condition(
        db, user.id, today, profile.age if profile else None, load_state=load
    )
    return AdminPreview(
        today=today,
        hunt=AdminPreviewHunt(**campaign_service.hunt_to_dict(hunt)) if hunt else None,
        load=AdminPreviewLoad(**load),
        condition=AdminPreviewCondition(**condition),
        progress=AdminPreviewProgress(**progress),
        scan_balance=AdminPreviewBalance(
            scan_credits=balance.scan_credits if balance else 0,
            has_unlimited=bool(balance.has_unlimited) if balance else False,
        ),
    )


def _data_health(db: Session, user_id: str, usage: UserUsageResponse) -> AdminDataHealth:
    """Repair-relevant counts; the facts ``usage`` already computed are reused."""
    total, soft_deleted, missing_local = db.query(
        func.count(WorkoutSession.id),
        count_where(WorkoutSession.deleted_at.isnot(None)),
        count_where((WorkoutSession.deleted_at.is_(None)) & (WorkoutSession.local_date.is_(None))),
    ).filter(WorkoutSession.user_id == user_id).one()
    custom, custom_without_family = db.query(
        func.count(Exercise.id), count_where(Exercise.family_id.is_(None))
    ).filter(Exercise.user_id == user_id, Exercise.is_custom == True).one()
    prs = db.query(func.count(PR.id)).filter(PR.user_id == user_id).scalar()
    return AdminDataHealth(
        sessions_total=int(total or 0) - int(soft_deleted or 0),
        sessions_soft_deleted=int(soft_deleted or 0),
        sessions_missing_local_date=int(missing_local or 0),
        custom_exercises=int(custom or 0),
        custom_exercises_without_family=int(custom_without_family or 0),
        bodyweight_entries=usage.integrations.bodyweight_entries,
        last_bodyweight_date=usage.integrations.last_bodyweight_date,
        prs_total=int(prs or 0),
        goals_by_status=usage.integrations.goals_by_status,
        gates_by_status=usage.gates_by_status,
        achievements_unlocked=usage.integrations.achievements_unlocked,
    )


def _integrations(usage: UserUsageResponse) -> AdminIntegrations:
    """The Integrations card, from the facts ``usage`` already computed."""
    u = usage.integrations
    return AdminIntegrations(
        whoop=AdminWhoopStatus(
            connected=u.whoop_connected,
            last_synced_at=u.whoop_last_synced_at,
            token_expires_at=u.whoop_token_expires_at,
            scope=u.whoop_scope,
        ),
        active_device_tokens=u.active_device_tokens,
        latest_daily_activity_date=usage.latest_daily_activity_date,
        daily_activity_sources_30d=[c.source for c in usage.activity_coverage],
    )


def get_user_detail(db: Session, user: User, *, today: Optional[date] = None) -> AdminUserDetailResponse:
    """Every card of the Hunter detail (spec §9.1 / §10.3).

    Composes the readers that already take a bare ``user_id``, every one in
    its read-only form: no balance or progress row is created, the load
    series is served as stored, no hunt is materialized. Renders for a
    brand-new account (no balance row, no campaign, no sessions) and for a
    soft-deleted one.
    """
    today = today or date.today()
    now = datetime.now(timezone.utc)
    user_id = user.id

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    balance = db.query(ScanBalance).filter(ScanBalance.user_id == user_id).first()
    purchases = (
        db.query(PurchaseRecord)
        .filter(PurchaseRecord.user_id == user_id)
        .order_by(PurchaseRecord.created_at.desc())
        .all()
    )
    campaign = campaign_service.get_active_campaign(db, user_id)
    limits = entitlement_service.effective_limits(db, user_id)
    defaults = entitlement_service.default_scan_limits()
    progress = xp_service.read_user_progress_summary(db, user_id)
    usage = admin_usage_service.user_usage(db, user_id, today=today)
    deleted_at = ensure_utc(user.deleted_at)

    return AdminUserDetailResponse(
        user=AdminUserIdentity(
            id=user.id,
            email=user.email,
            username=user.username,
            created_at=user.created_at,
            updated_at=user.updated_at,
            is_deleted=bool(user.is_deleted),
            deleted_at=user.deleted_at,
            purge_eligible_at=(
                purge_service.purge_eligible_at(deleted_at)
                if user.is_deleted and deleted_at is not None
                else None
            ),
            is_admin=bool(user.is_admin),
            token_version=int(user.token_version or 0),
            admin_failed_logins=int(user.admin_failed_logins or 0),
            admin_locked_until=user.admin_locked_until,
        ),
        profile=AdminProfile.model_validate(profile, from_attributes=True) if profile else None,
        progress=progress,
        balance=AdminBalanceBlock(
            exists=balance is not None,
            scan_credits=balance.scan_credits if balance else None,
            has_unlimited=bool(balance.has_unlimited) if balance else False,
            free_scans_reset_at=balance.free_scans_reset_at if balance else None,
            purchases=[AdminPurchaseRow.model_validate(p, from_attributes=True) for p in purchases],
        ),
        entitlements=[
            entitlement_response(row, now)
            for row in entitlement_service.list_entitlements(db, user_id)
        ],
        effective_limits=AdminEffectiveLimits(
            daily_limit=limits.daily_limit,
            cooldown_seconds=limits.cooldown_seconds,
            free_monthly=limits.free_monthly,
            defaults=defaults.__dict__,
        ),
        campaign=_campaign_summary(db, campaign, today) if campaign else None,
        integrations=_integrations(usage),
        data_health=_data_health(db, user_id, usage),
        preview=_preview(
            db, user, today, profile=profile, balance=balance, campaign=campaign, progress=progress
        ),
        recent_audit=[
            AuditEntry.model_validate(row, from_attributes=True)
            for row in _audit_query(db, target_id=user_id).limit(10).all()
        ],
        usage=usage,
    )


# ── mutations (spec §4.5, §6.3-6.4, §7, §8.1) ───────────────────────────────

# ``|delta|`` above this is destructive tier (spec §4.5).
CREDITS_STEP_UP_THRESHOLD = 50

USER_STATE_FIELDS = ("is_deleted", "deleted_at", "token_version")
ENTITLEMENT_FIELDS = ("id", "key", "value", "source", "granted_by", "purchase_record_id", "expires_at", "revoked_at")
PRODUCT_FIELDS = ("id", "kind", "credits", "entitlement_key", "display_name", "active", "sort_order")


def _user_state(user: User) -> AdminUserStateResponse:
    return AdminUserStateResponse(id=user.id, is_deleted=bool(user.is_deleted), deleted_at=user.deleted_at)


# ── credits (spec §7.1) ──

def _prior_adjust(db: Session, actor: User, idempotency_key: str) -> Optional[AdminAuditLog]:
    return (
        db.query(AdminAuditLog)
        .filter(
            AdminAuditLog.actor_user_id == actor.id,
            AdminAuditLog.idempotency_key == idempotency_key,
            AdminAuditLog.action == "credits.adjust",
        )
        .first()
    )


def _replay(prior: AdminAuditLog, digest: str) -> CreditsAdjustResponse:
    """The stored result for a repeated ``Idempotency-Key``; 422 if the body changed."""
    if prior.body_sha256 != digest:
        raise unprocessable("Idempotency-Key was already used with a different body")
    return CreditsAdjustResponse(
        scan_credits_before=int((prior.before or {})["scan_credits"]),
        scan_credits_after=int((prior.after or {})["scan_credits"]),
        audit_id=prior.id,
        replayed=True,
    )


def adjust_credits(
    db: Session,
    *,
    actor: User,
    user: User,
    delta: int,
    reason: str,
    password: Optional[str],
    idempotency_key: str,
    request: Optional[Request] = None,
) -> CreditsAdjustResponse:
    """Add ``delta`` to the user's balance under the scanner's row lock.

    The audit row is the idempotency record: the same key with the same
    body replays the stored result (``replayed=True``), the same key with a
    different body is 422, and the partial unique index makes a concurrent
    duplicate lose the race and replay too. A result below zero is 409.
    ``|delta| > CREDITS_STEP_UP_THRESHOLD`` re-verifies the password first.
    """
    digest = body_hash({"user_id": user.id, "delta": delta, "reason": reason})
    prior = _prior_adjust(db, actor, idempotency_key)
    if prior is not None:
        return _replay(prior, digest)

    if abs(delta) > CREDITS_STEP_UP_THRESHOLD:
        verify_step_up(db, actor, password)

    balance = entitlement_service.get_or_create_balance(db, user.id, for_update=True, commit=False)
    before = int(balance.scan_credits)
    after = before + delta
    if after < 0:
        raise conflict(f"Balance would go negative: {before} {delta:+d}")
    balance.scan_credits = after
    try:
        row = audit(
            db,
            actor=actor,
            action="credits.adjust",
            target_type="user",
            target_id=user.id,
            before={"scan_credits": before},
            after={"scan_credits": after, "delta": delta},
            reason=reason,
            request=request,
            idempotency_key=idempotency_key,
            body_sha256=digest,
        )
    except IntegrityError:
        # A concurrent request with the same key committed first: drop our
        # change and hand back its result.
        db.rollback()
        prior = _prior_adjust(db, actor, idempotency_key)
        if prior is None:
            raise
        return _replay(prior, digest)
    return CreditsAdjustResponse(
        scan_credits_before=before, scan_credits_after=after, audit_id=row.id, replayed=False
    )


# ── entitlements (spec §6.3) ──

def grant_entitlement(
    db: Session,
    *,
    actor: User,
    user: User,
    key: str,
    value: Any,
    expires_at: Optional[datetime],
    reason: str,
    request: Optional[Request] = None,
) -> EntitlementResponse:
    """An ``admin_grant`` row (the schema validated key and value); audits ``entitlement.grant``."""
    row = entitlement_service.grant(
        db,
        user_id=user.id,
        key=key,
        value=value,
        source=EntitlementSource.ADMIN_GRANT,
        granted_by=actor.id,
        reason=reason,
        expires_at=to_naive_utc(expires_at) if expires_at is not None else None,
    )
    audit(
        db,
        actor=actor,
        action="entitlement.grant",
        target_type="user",
        target_id=user.id,
        after=snapshot(row, ENTITLEMENT_FIELDS),
        reason=reason,
        request=request,
    )
    return entitlement_response(row)


def revoke_entitlement(
    db: Session,
    *,
    actor: User,
    user: User,
    entitlement_id: str,
    password: Optional[str],
    reason: str,
    request: Optional[Request] = None,
) -> EntitlementResponse:
    """Destructive tier. 404 unless the row belongs to ``user``; 409 if already revoked."""
    verify_step_up(db, actor, password)
    row = (
        db.query(UserEntitlement)
        .filter(UserEntitlement.id == entitlement_id, UserEntitlement.user_id == user.id)
        .first()
    )
    if row is None:
        raise not_found("Entitlement not found")
    if row.revoked_at is not None:
        raise conflict("Entitlement is already revoked")
    before = snapshot(row, ENTITLEMENT_FIELDS)
    entitlement_service.revoke(db, row)
    audit(
        db,
        actor=actor,
        action="entitlement.revoke",
        target_type="user",
        target_id=user.id,
        before=before,
        after=snapshot(row, ENTITLEMENT_FIELDS),
        reason=reason,
        request=request,
    )
    return entitlement_response(row)


# ── soft-delete / restore (spec §8.1) ──

def _set_deleted(
    db: Session,
    *,
    actor: User,
    user: User,
    deleted: bool,
    password: Optional[str],
    reason: str,
    request: Optional[Request],
) -> AdminUserStateResponse:
    """Soft-delete (``deleted=True``) or restore one account (spec §8.1).

    Destructive tier; refuses self and other admins; 409 when already in the
    requested state. Deleting mirrors ``DELETE /auth/account`` without the
    user's password (the next request 401s, login 403s); restoring bumps
    ``token_version`` so pre-deletion tokens die (§4.3).
    """
    verify_step_up(db, actor, password)
    protect_account(actor, user)
    if bool(user.is_deleted) == deleted:
        raise conflict("Account is already soft-deleted" if deleted else "Account is not soft-deleted")
    before = snapshot(user, USER_STATE_FIELDS)
    user.is_deleted = deleted
    user.deleted_at = utcnow() if deleted else None
    if not deleted:
        user.token_version = int(user.token_version or 0) + 1
    db.flush()
    audit(
        db,
        actor=actor,
        action="user.soft_delete" if deleted else "user.restore",
        target_type="user",
        target_id=user.id,
        before=before,
        after=snapshot(user, USER_STATE_FIELDS),
        reason=reason,
        request=request,
    )
    return _user_state(user)


def soft_delete_user(
    db: Session, *, actor: User, user: User, password: Optional[str], reason: str,
    request: Optional[Request] = None,
) -> AdminUserStateResponse:
    return _set_deleted(db, actor=actor, user=user, deleted=True, password=password, reason=reason, request=request)


def restore_user(
    db: Session, *, actor: User, user: User, password: Optional[str], reason: str,
    request: Optional[Request] = None,
) -> AdminUserStateResponse:
    return _set_deleted(db, actor=actor, user=user, deleted=False, password=password, reason=reason, request=request)


# ── products (spec §6.4) ──

def upsert_product(
    db: Session,
    *,
    actor: User,
    body: ProductUpsertRequest,
    product_id: Optional[str] = None,
    request: Optional[Request] = None,
) -> ProductResponse:
    """``POST`` (``product_id`` None) creates; ``PATCH`` edits the row at ``product_id``.

    The id is immutable (422 when the body disagrees with the path) and
    rows are never deleted — ``active=false`` is the destructive-tier
    deactivation. The schema validates ``entitlement_key`` against the registry.
    """
    if not body.active:
        verify_step_up(db, actor, body.password)
    fields = {name: getattr(body, name) for name in PRODUCT_FIELDS}

    existing = entitlement_service.get_product(db, body.id)
    if product_id is None:
        if existing is not None:
            raise conflict(f"Product {body.id} already exists")
        product = Product(**fields)
        db.add(product)
        before = None
    else:
        if body.id != product_id:
            raise unprocessable("Product id is immutable")
        if existing is None:
            raise not_found("Product not found")
        product = existing
        before = snapshot(product, PRODUCT_FIELDS)
        for name, value in fields.items():
            setattr(product, name, value)
    db.flush()
    audit(
        db,
        actor=actor,
        action="product.upsert",
        target_type="product",
        target_id=product.id,
        before=before,
        after=snapshot(product, PRODUCT_FIELDS),
        reason=body.reason,
        request=request,
    )
    return ProductResponse.model_validate(product, from_attributes=True)


# ── support actions (spec §7.2-7.4) ──

def backfill_families(
    db: Session,
    *,
    actor: User,
    dry_run: bool,
    password: Optional[str],
    reason: str,
    request: Optional[Request] = None,
) -> FamilyBackfillResponse:
    """``scripts/backfill_exercise_families.py`` as a route (spec §7.3).

    The dry run (default) reports what an apply would change and writes
    nothing; apply is destructive tier and audits ``maintenance.family_backfill``.
    """
    if not dry_run:
        verify_step_up(db, actor, password)
    families_changed = ensure_families(db, dry_run=dry_run, commit=False)
    rows = db.query(Exercise).order_by(Exercise.is_custom.desc(), Exercise.name).all()
    updates = planned_family_updates(db, dry_run=dry_run, rows=rows)
    exercises_updated = len(updates) if dry_run else apply_family_updates(db, updates, commit=False)
    planned = {ex.id for ex, _ in updates}
    unresolved = [
        UnresolvedExercise(name=ex.name, is_custom=bool(ex.is_custom), user_id=ex.user_id)
        for ex in rows
        if ex.family_id is None and ex.id not in planned
    ]
    result = FamilyBackfillResponse(
        dry_run=dry_run,
        families_changed=families_changed,
        exercises_updated=exercises_updated,
        assigned=len(rows) - len(unresolved),
        total=len(rows),
        unresolved=unresolved,
    )
    if not dry_run:
        audit(
            db,
            actor=actor,
            action="maintenance.family_backfill",
            target_type="system",
            after={**result.model_dump(exclude={"unresolved", "dry_run"}), "unresolved": len(unresolved)},
            reason=reason,
            request=request,
        )
    return result


def seed_achievements(db: Session, *, actor: User, reason: str, request: Optional[Request] = None) -> int:
    """The audited twin of the public ``POST /progress/seed-achievements`` (spec §7.4)."""
    seeded = seed_achievement_definitions(db, commit=False)
    audit(
        db,
        actor=actor,
        action="maintenance.seed_achievements",
        target_type="system",
        after={"seeded": seeded},
        reason=reason,
        request=request,
    )
    return seeded


def _arc_previews(arcs: List[Dict[str, Any]]) -> List[ArcPreview]:
    return [ArcPreview(**{**arc, "templates": len(arc["templates"])}) for arc in arcs]


def import_campaign_for_user(
    db: Session,
    *,
    actor: User,
    user: User,
    body: AdminCampaignImportRequest,
    request: Optional[Request] = None,
) -> Dict[str, Any]:
    """``scripts/import_training_calendar.py`` for a target user (spec §7.2).

    Phases come from the body or a committed template. A dry run parses
    only and returns ``arcs_preview``. Apply is ``campaign_service.apply_import``
    — the same path as ``POST /campaign/import`` (409 when a campaign is
    active unless ``replace``, which is destructive tier because the old
    campaign's future planned hunts are deleted) — plus one
    ``campaign.import`` audit row on the user carrying the raw payload for replay.
    """
    if body.replace and not body.dry_run:
        verify_step_up(db, actor, body.password)
    phases = (
        [p.model_dump() for p in body.phases]
        if body.phases is not None
        else campaign_templates.load_template(body.template)
    )

    if body.dry_run:
        active = campaign_service.get_active_campaign(db, user.id)
        arcs, warnings = campaign_service.preview_import(db, phases)
        if active is not None and not body.replace:
            warnings.append("an active campaign exists — apply will 409 unless replace=true")
        return {
            "dry_run": True,
            "arcs_preview": _arc_previews(arcs),
            "warnings": warnings,
            "retired_campaign_id": active.id if (active and body.replace) else None,
        }

    try:
        result, payload = campaign_service.apply_import(
            db,
            user.id,
            name=body.name,
            phases=phases,
            objectives=body.objectives,
            start_date=body.start_date,
            client_date=body.client_date,
            goal=body.goal,
            replace=body.replace,
        )
    except campaign_service.ActiveCampaignExists:
        raise conflict("An active campaign already exists; send replace=true to retire it.")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    retired = result.retired_campaign_id
    audit(
        db,
        actor=actor,
        action="campaign.import",
        target_type="user",
        target_id=user.id,
        before={"active_campaign_id": retired, "status": "active" if retired else None},
        after={
            "campaign_id": result.campaign.id,
            "arcs": len(result.campaign.arcs),
            "templates_created": result.templates_created,
            "objectives_created": result.objectives_created,
            "retired_campaign_id": retired,
            "planned_hunts_deleted": result.planned_hunts_deleted,
            "warnings": len(result.warnings),
            "payload": body.model_dump(mode="json", exclude={"password"}),
        },
        reason=body.reason,
        request=request,
    )
    payload.update(
        dry_run=False,
        retired_campaign_id=retired,
        planned_hunts_deleted=result.planned_hunts_deleted,
    )
    return payload
