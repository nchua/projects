"""
Admin read surfaces (control-plane spec §9): the Hunters list, the Hunter
detail composed from every existing reader in its read-only form, the
audit page, and the catalog. Readers never create rows — a test counts
every table before and after the detail GET. Mutations live in
``admin_mutation_service``; the session mint in ``admin_session_service``.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Subquery, func, or_, select
from sqlalchemy.orm import Query, Session

from app.core.utils import ensure_utc
from app.models.admin import AdminAuditLog
from app.models.campaign import Campaign
from app.models.entitlement import Product, UserEntitlement
from app.models.exercise import Exercise
from app.models.pr import PR
from app.models.progress import UserProgress
from app.models.scan_balance import PurchaseRecord, ScanBalance
from app.models.user import User, UserProfile
from app.models.workout import WorkoutSession
from app.schemas.admin import (
    AdminBalanceBlock,
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
    AdminWhoopStatus,
    AuditEntry,
    EntitlementResponse,
    ProductResponse,
    UserSort,
    UserUsageResponse,
)
from app.services import (
    admin_usage_service,
    campaign_service,
    condition_service,
    entitlement_service,
    purge_service,
    training_load_service,
    xp_service,
)
from app.services.admin_usage_service import count_where
from app.services.training_load_service import local_day_sql

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
