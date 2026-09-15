"""
Admin read surfaces (control-plane spec §9): the Hunters list, the Hunter
detail composed from every existing reader in its read-only form, the
audit page, and the catalog. Readers never create rows — a test counts
every table before and after the detail GET. Mutations live in
``admin_mutation_service``; the session mint in ``admin_session_service``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import Date, Integer, String, Subquery, and_, case, cast, func, or_, select
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.core.settings_registry import (
    INACTIVE_AFTER_DAYS,
    SETTINGS,
    SettingSpec,
)
from app.core.utils import ensure_utc, split_csv, to_naive_utc, utcnow
from app.models.admin import AdminAuditLog
from app.models.app_setting import AppSetting
from app.models.campaign import Campaign
from app.models.entitlement import Product, UserEntitlement
from app.models.exercise import Exercise
from app.models.pr import PR
from app.models.progress import UserProgress
from app.models.scan_balance import PurchaseRecord, ScanBalance
from app.models.screenshot_usage import ScreenshotUsage
from app.models.user import User, UserProfile
from app.models.workout import WorkoutSession
from app.schemas.admin import (
    AdminAccountBlock,
    AdminActivityRow,
    AdminBalanceBlock,
    AdminCampaignSummary,
    AdminDataHealth,
    AdminEffectiveLimits,
    AdminIntegrations,
    AdminPlanBlock,
    AdminPlanChange,
    AdminPreview,
    AdminPreviewBalance,
    AdminPreviewCondition,
    AdminPreviewHunt,
    AdminPreviewLoad,
    AdminPreviewProgress,
    AdminProfile,
    AdminPurchaseRow,
    AdminScansBlock,
    AdminUserDetailResponse,
    AdminUserIdentity,
    AdminUserRow,
    AdminWhoopStatus,
    AuditEntry,
    EntitlementResponse,
    EnvAdmin,
    EnvBuild,
    EnvIntegrations,
    ProductResponse,
    SettingRow,
    SettingsEnvBlock,
    SettingsResponse,
    UserSort,
    UserUsageResponse,
)
from app.services import (
    admin_usage_service,
    campaign_service,
    condition_service,
    entitlement_service,
    notification_service,
    purge_service,
    settings_service,
    training_load_service,
    whoop_service,
    xp_service,
)
from app.services.admin_usage_service import SCANS_4WK_DAYS, count_where
from app.services.entitlement_service import (
    KEY_FREE_MONTHLY,
    KEY_UNLIMITED,
    OVERRIDE_KEYS,
    PLAN_CREDITS,
    PLAN_FREE,
    PLAN_ORDER,
    PLAN_OVERRIDE,
    PLAN_UNLIMITED,
    Plan,
    active_clauses,
    plan_snapshot,
)
from app.services.training_load_service import local_day_sql, session_local_day

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_DELETED = "deleted"
STATUS_PURGE_ELIGIBLE = "purge_eligible"
# Display / sort order of the four statuses (``sort=status`` ascending).
STATUS_ORDER: Tuple[str, ...] = (STATUS_ACTIVE, STATUS_INACTIVE, STATUS_DELETED, STATUS_PURGE_ELIGIBLE)
DEFAULT_STATUSES: Tuple[str, ...] = (STATUS_ACTIVE, STATUS_INACTIVE)  # "not deleted" (§4.3)

ACTIVITY_LIMIT = 20
# The audit actions that change a hunter's plan (the Plan card's "last change").
PLAN_AUDIT_ACTIONS: Tuple[str, ...] = (
    "user.plan_change", "credits.adjust", "entitlement.grant", "entitlement.revoke",
)

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
            func.max(local_day_sql()).label("last_workout"),
        )
        .where(WorkoutSession.deleted_at.is_(None))
        .group_by(WorkoutSession.user_id)
        .subquery()
    )


def _scans_rollup(since: datetime) -> Subquery:
    """Per-user scan count since ``since`` + the last scan day, as a subquery."""
    return (
        select(
            ScreenshotUsage.user_id.label("user_id"),
            count_where(ScreenshotUsage.created_at >= since).label("scans_4wk"),
            func.max(func.date(ScreenshotUsage.created_at, type_=Date)).label("last_scan"),
        )
        .group_by(ScreenshotUsage.user_id)
        .subquery()
    )


# ── the status model (console v2 §3.3, §6.1) ──

@dataclass(frozen=True)
class StatusThresholds:
    """The two numbers ``status_for`` needs, resolved once per page."""

    inactive_after_days: int
    grace_days: int

    def purge_cutoff(self, now: datetime) -> datetime:
        return now - timedelta(days=self.grace_days)

    def inactive_cutoff(self, now: datetime) -> date:
        return now.date() - timedelta(days=self.inactive_after_days)


def status_thresholds(db: Session) -> StatusThresholds:
    return StatusThresholds(
        inactive_after_days=int(settings_service.get(db, INACTIVE_AFTER_DAYS)),
        grace_days=purge_service.grace_days(db),
    )


def status_for(user: User, last_active: Optional[date], now: datetime, thresholds: StatusThresholds) -> str:
    """``active | inactive | deleted | purge_eligible`` for one loaded row (§3.3).

    The purge leg is ``purge_service.is_purge_eligible_at`` (admins are never
    purge-eligible); the SQL in ``_derived`` is the twin, and a test asserts
    the two agree on a seeded page.
    """
    if user.is_deleted:
        eligible = purge_service.is_purge_eligible_at(user, thresholds.purge_cutoff(now))
        return STATUS_PURGE_ELIGIBLE if eligible else STATUS_DELETED
    if last_active is not None and last_active >= thresholds.inactive_cutoff(now):
        return STATUS_ACTIVE
    return STATUS_INACTIVE


def last_active_of(
    workout_day: Optional[date], scan_day: Optional[date], login_at: Optional[datetime]
) -> Tuple[Optional[date], Optional[str]]:
    """``max`` of the three activity legs as a day, plus which leg won (workout > scan > login on ties)."""
    login_day = ensure_utc(login_at).date() if login_at is not None else None
    legs = [("workout", workout_day), ("scan", scan_day), ("login", login_day)]
    best = max((d for _, d in legs if d is not None), default=None)
    if best is None:
        return None, None
    return best, next(kind for kind, d in legs if d == best)


def _pair_max(x: ColumnElement, y: ColumnElement) -> ColumnElement:
    """NULL-tolerant ``max(x, y)`` as a CASE — the same on SQLite and Postgres."""
    return case((y.is_(None), x), (x.is_(None), y), (x >= y, x), else_=y)


def _newest_active_value(key: str, now: datetime) -> ColumnElement:
    """Correlated scalar: the user's newest active row value for ``key``, as text."""
    return (
        select(cast(UserEntitlement.value, String))
        .where(UserEntitlement.user_id == User.id, UserEntitlement.key == key, *active_clauses(now))
        .order_by(UserEntitlement.created_at.desc(), UserEntitlement.id.desc())
        .limit(1)
        .correlate_except(UserEntitlement)
        .scalar_subquery()
    )


def _has_active_override(now: datetime) -> ColumnElement:
    return (
        select(UserEntitlement.id)
        .where(UserEntitlement.user_id == User.id, UserEntitlement.key.in_(OVERRIDE_KEYS), *active_clauses(now))
        .correlate_except(UserEntitlement)
        .exists()
    )


def _rank(expr: ColumnElement, order: Sequence[str]) -> ColumnElement:
    return case(*((expr == name, i) for i, name in enumerate(order)), else_=len(order))


def _derived(*, now: datetime, default_free: int, thresholds: StatusThresholds) -> Subquery:
    """One row per user with the SQL twins of ``plans_for`` / ``status_for`` and the
    activity rollups (§6.2) — computed once here so filters, sorts and the count
    reference plain columns instead of re-evaluating the correlated subqueries."""
    sessions = (
        select(
            WorkoutSession.user_id.label("user_id"),
            func.count(WorkoutSession.id).label("session_count"),
            func.max(local_day_sql()).label("last_workout"),
        )
        .where(WorkoutSession.deleted_at.is_(None))
        .group_by(WorkoutSession.user_id)
        .subquery()
    )
    scans = (
        select(
            ScreenshotUsage.user_id.label("user_id"),
            count_where(ScreenshotUsage.created_at >= to_naive_utc(now - timedelta(days=SCANS_4WK_DAYS))).label("scans_4wk"),
            func.max(func.date(ScreenshotUsage.created_at, type_=Date)).label("last_scan"),
        )
        .group_by(ScreenshotUsage.user_id)
        .subquery()
    )

    unlimited = _newest_active_value(KEY_UNLIMITED, now) == "true"
    effective_free = func.coalesce(cast(_newest_active_value(KEY_FREE_MONTHLY, now), Integer), default_free)
    plan = case(
        (unlimited, PLAN_UNLIMITED),
        (_has_active_override(now), PLAN_OVERRIDE),
        (func.coalesce(ScanBalance.scan_credits, 0) > effective_free, PLAN_CREDITS),
        else_=PLAN_FREE,
    )
    last_login = func.date(User.last_login_at, type_=Date)
    last_active = _pair_max(_pair_max(sessions.c.last_workout, scans.c.last_scan), last_login)
    kind = case(
        (last_active.is_(None), None),
        (sessions.c.last_workout == last_active, "workout"),
        (scans.c.last_scan == last_active, "scan"),
        else_="login",
    )
    status = case(
        (and_(*purge_service.eligible_filter_at(to_naive_utc(thresholds.purge_cutoff(now)))), STATUS_PURGE_ELIGIBLE),
        (User.is_deleted == True, STATUS_DELETED),
        (last_active >= thresholds.inactive_cutoff(now), STATUS_ACTIVE),
        else_=STATUS_INACTIVE,
    )
    return (
        select(
            User.id.label("user_id"),
            plan.label("plan"),
            status.label("status"),
            last_active.label("last_active"),
            kind.label("last_active_kind"),
            func.coalesce(sessions.c.session_count, 0).label("session_count"),
            sessions.c.last_workout.label("last_workout"),
            func.coalesce(scans.c.scans_4wk, 0).label("scans_4wk"),
            ScanBalance.scan_credits.label("scan_credits"),
            ScanBalance.has_unlimited.label("has_unlimited"),
        )
        .select_from(User)
        .outerjoin(sessions, sessions.c.user_id == User.id)
        .outerjoin(scans, scans.c.user_id == User.id)
        .outerjoin(ScanBalance, ScanBalance.user_id == User.id)
        .subquery()
    )


def parse_csv(value: Optional[str], allowed: Iterable[str], name: str) -> Optional[List[str]]:
    """``a,b`` → ``["a", "b"]`` validated against ``allowed``; ``ValueError`` names the bad token."""
    if value is None:
        return None
    allowed = tuple(allowed)
    tokens = split_csv(value)
    if not tokens:
        raise ValueError(f"{name} needs at least one value")
    for token in tokens:
        if token not in allowed:
            raise ValueError(f"unknown {name} {token!r} (one of {', '.join(allowed)})")
    return tokens


def _resolve_filters(
    statuses: Optional[List[str]], plans: Optional[List[str]],
    deleted: Optional[bool], unlimited: Optional[bool],
) -> Tuple[List[str], Optional[List[str]]]:
    """v2 ``status`` / ``plan`` win; the v1 ``deleted`` / ``unlimited`` flags map onto them (§6.2)."""
    if statuses is None:
        statuses = [STATUS_DELETED, STATUS_PURGE_ELIGIBLE] if deleted else list(DEFAULT_STATUSES)
    if plans is None and unlimited is not None:
        plans = [PLAN_UNLIMITED] if unlimited else [p for p in PLAN_ORDER if p != PLAN_UNLIMITED]
    return statuses, plans


def list_users(
    db: Session,
    *,
    q: Optional[str] = None,
    statuses: Optional[List[str]] = None,
    plans: Optional[List[str]] = None,
    joined_days: Optional[int] = None,
    deleted: Optional[bool] = None,
    unlimited: Optional[bool] = None,
    active_days: Optional[int] = None,
    sort: UserSort = "last_active",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    now: Optional[datetime] = None,
) -> Tuple[List[AdminUserRow], int]:
    """The Hunters table (v1 §9.1, console v2 §6.2): filters, sort, offset paging, total.

    Filters and sorts on ``plan`` / ``status`` / ``last_active`` run in SQL
    over the ``_derived`` subquery; the rows themselves display ``plans_for``
    and ``status_for``, the canonical definitions, and a test asserts the two
    agree. Per page: one row query, one filters-only count, and the batched
    ``plans_for`` reads — never one per user.
    """
    now = now or utcnow()
    thresholds = status_thresholds(db)
    default_free = int(settings_service.get(db, "FREE_MONTHLY_SCANS"))
    d = _derived(now=now, default_free=default_free, thresholds=thresholds)

    query = (
        db.query(User, UserProgress.level, UserProgress.rank, d)
        .join(d, d.c.user_id == User.id)
        .outerjoin(UserProgress, UserProgress.user_id == User.id)
    )
    if q:
        needle = f"%{_escape_like(q.strip())}%"
        query = query.filter(or_(
            User.email.ilike(needle, escape="\\"),
            User.username.ilike(needle, escape="\\"),
            User.id.ilike(needle, escape="\\"),
        ))
    statuses, plans = _resolve_filters(statuses, plans, deleted, unlimited)
    if set(statuses) != set(STATUS_ORDER):
        query = query.filter(d.c.status.in_(statuses))
    if plans is not None and set(plans) != set(PLAN_ORDER):
        query = query.filter(d.c.plan.in_(plans))
    if joined_days is not None:
        query = query.filter(User.created_at >= to_naive_utc(now - timedelta(days=joined_days)))
    if active_days is not None:
        query = query.filter(d.c.last_workout >= now.date() - timedelta(days=active_days))

    total = query.with_entities(func.count(User.id)).order_by(None).scalar()

    sort_column = {
        "last_active": d.c.last_active,
        "created": User.created_at,
        "created_at": User.created_at,
        "email": User.email,
        "credits": d.c.scan_credits,
        "plan": _rank(d.c.plan, PLAN_ORDER),
        "status": _rank(d.c.status, STATUS_ORDER),
        "scans_4wk": d.c.scans_4wk,
        "level": UserProgress.level,
        "session_count": d.c.session_count,
    }[sort]
    primary = sort_column.desc() if order == "desc" else sort_column.asc()
    rows = query.order_by(primary.nulls_last(), User.id).offset(offset).limit(limit).all()

    plans_by_id = entitlement_service.plans_for(db, [row[0].id for row in rows], default_free=default_free)
    items: List[AdminUserRow] = []
    for user, level, rank, *derived in rows:
        row = dict(zip(d.c.keys(), derived))
        plan = plans_by_id[user.id]
        items.append(AdminUserRow(
            id=user.id,
            email=user.email,
            username=user.username,
            created_at=user.created_at,
            is_deleted=bool(user.is_deleted),
            deleted_at=user.deleted_at,
            is_admin=bool(user.is_admin),
            level=level,
            rank=rank,
            last_workout_date=row["last_workout"],
            session_count=int(row["session_count"] or 0),
            scan_credits=plan.scan_credits,
            has_unlimited=bool(row["has_unlimited"]),
            plan=plan.plan,
            plan_source=plan.plan_source,
            plan_expires_at=plan.expires_at,
            purchased_credits=plan.purchased_credits,
            free_monthly=plan.free_monthly,
            status=status_for(user, row["last_active"], now, thresholds),
            last_active=row["last_active"],
            last_active_kind=row["last_active_kind"],
            scans_4wk=int(row["scans_4wk"] or 0),
            override_keys=list(plan.override_keys),
        ))
    return items, int(total or 0)


def _audit_query(
    db: Session,
    *,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    action: Optional[str] = None,
    request_id: Optional[str] = None,
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
    if request_id:
        query = query.filter(AdminAuditLog.request_id == request_id)  # exact: one batch = one request (§5.4)
    return query.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())


def list_audit(
    db: Session,
    *,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    action: Optional[str] = None,
    request_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[AuditEntry], int]:
    """Newest-first page of the append-only audit log (spec §5), with the total."""
    query = _audit_query(
        db, target_type=target_type, target_id=target_id, actor_user_id=actor_user_id, action=action,
        request_id=request_id,
    )
    rows = query.offset(offset).limit(limit).all()
    return [AuditEntry.model_validate(row, from_attributes=True) for row in rows], int(query.count())


def list_products(db: Session) -> List[ProductResponse]:
    """The catalog, active or not, in display order, with what each SKU has sold (§4.6)."""
    rows = db.query(Product).order_by(Product.sort_order, Product.id).all()
    sold: Dict[str, Tuple[int, int]] = {
        product_id: (int(n or 0), int(verified or 0))
        for product_id, n, verified in db.query(
            PurchaseRecord.product_id, func.count(PurchaseRecord.id), count_where(PurchaseRecord.verified == True)
        ).group_by(PurchaseRecord.product_id).all()
    }
    out = []
    for p in rows:
        response = ProductResponse.model_validate(p, from_attributes=True)
        response.sold, response.sold_verified = sold.get(p.id, (0, 0))
        out.append(response)
    return out


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
    now = utcnow()
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
    defaults = entitlement_service.default_scan_limits(db)
    limits = entitlement_service.effective_limits(db, user_id, base=defaults)
    progress = xp_service.read_user_progress_summary(db, user_id)
    usage = admin_usage_service.user_usage(db, user_id, today=today)
    deleted_at = ensure_utc(user.deleted_at)
    plan = entitlement_service.plans_for(db, [user_id], default_free=defaults.free_monthly)[user_id]
    thresholds = status_thresholds(db)
    last_active, last_active_kind = last_active_of(
        db.query(func.max(local_day_sql())).filter(
            WorkoutSession.user_id == user_id, WorkoutSession.deleted_at.is_(None)
        ).scalar(),
        db.query(func.max(func.date(ScreenshotUsage.created_at, type_=Date)))
        .filter(ScreenshotUsage.user_id == user_id).scalar(),
        user.last_login_at,
    )
    purge_at = (
        deleted_at + timedelta(days=thresholds.grace_days)
        if user.is_deleted and deleted_at is not None
        else None
    )
    audit_rows = _audit_query(db, target_id=user_id).limit(ACTIVITY_LIMIT).all()

    return AdminUserDetailResponse(
        user=AdminUserIdentity(
            id=user.id,
            email=user.email,
            username=user.username,
            created_at=user.created_at,
            updated_at=user.updated_at,
            is_deleted=bool(user.is_deleted),
            deleted_at=user.deleted_at,
            purge_eligible_at=purge_at,
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
        recent_audit=[AuditEntry.model_validate(row, from_attributes=True) for row in audit_rows[:10]],
        usage=usage,
        plan=_plan_block(db, user_id, plan, audit_rows),
        account=AdminAccountBlock(
            status=status_for(user, last_active, now, thresholds),
            purge_at=purge_at,
            last_active=last_active,
            last_active_kind=last_active_kind,
            last_login_at=user.last_login_at,
            token_version=int(user.token_version or 0),
            admin_locked_until=user.admin_locked_until,
        ),
        scans=_scans_block(db, user_id, plan, balance, limits, now),
        activity=_activity(db, user, audit_rows),
    )


# ── console v2 detail blocks (§6.3) ──

def _plan_block(db: Session, user_id: str, plan: Plan, recent: List[AdminAuditLog]) -> AdminPlanBlock:
    """The Plan card: the derived plan plus the newest plan-affecting audit row.

    ``recent`` (the detail's newest audit rows) is scanned first; only when
    none of them changed the plan does a targeted query look further back.
    """
    row = next((r for r in recent if r.action in PLAN_AUDIT_ACTIONS), None)
    if row is None and len(recent) == ACTIVITY_LIMIT:
        row = _audit_query(db, target_id=user_id).filter(AdminAuditLog.action.in_(PLAN_AUDIT_ACTIONS)).first()
    last_change = (
        AdminPlanChange(at=row.created_at, actor=row.actor_user_id, action=row.action, reason=row.reason, audit_id=row.id)
        if row is not None
        else None
    )
    return AdminPlanBlock(**plan_snapshot(plan), last_change=last_change)


def _scans_block(
    db: Session, user_id: str, plan: Plan, balance: Optional[ScanBalance],
    limits: entitlement_service.ScanLimits, now: datetime,
) -> AdminScansBlock:
    """The Scans card: balance, the free grant and its reset, recent use, the caps in force."""
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def since(instant: datetime) -> Any:
        return count_where(ScreenshotUsage.created_at >= to_naive_utc(instant))

    used_7d, used_4wk, today_count = (
        db.query(since(now - timedelta(days=7)), since(now - timedelta(days=SCANS_4WK_DAYS)), since(today_start))
        .filter(ScreenshotUsage.user_id == user_id)
        .one()
    )
    return AdminScansBlock(
        scan_credits=plan.scan_credits,
        purchased_credits=plan.purchased_credits,
        free_monthly=plan.free_monthly,
        free_scans_reset_at=balance.free_scans_reset_at if balance else None,
        used_7d=int(used_7d or 0),
        used_4wk=int(used_4wk or 0),
        today_count=int(today_count or 0),
        daily_limit=limits.daily_limit,
        cooldown_seconds=limits.cooldown_seconds,
    )


def _activity(db: Session, user: User, audit_rows: List[AdminAuditLog]) -> List[AdminActivityRow]:
    """The last ``ACTIVITY_LIMIT`` of: audit rows on this target, sessions, scans, the last login (§6.3)."""
    rows: List[AdminActivityRow] = [
        AdminActivityRow(
            at=a.created_at, kind="audit", summary=a.action, actor=a.actor_user_id, audit_id=a.id
        )
        for a in audit_rows
    ]
    sessions = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.user_id == user.id, WorkoutSession.deleted_at.is_(None))
        .order_by(WorkoutSession.date.desc())
        .limit(ACTIVITY_LIMIT)
        .all()
    )
    for session in sessions:
        day = session_local_day(session)
        label = session.name or session.activity_type or "Session"
        rows.append(AdminActivityRow(at=session.date, kind="session", summary=f"{label} · {day.isoformat()}"))
    scans = (
        db.query(ScreenshotUsage)
        .filter(ScreenshotUsage.user_id == user.id)
        .order_by(ScreenshotUsage.created_at.desc())
        .limit(ACTIVITY_LIMIT)
        .all()
    )
    for scan in scans:
        n = int(scan.screenshots_count or 1)
        rows.append(AdminActivityRow(at=scan.created_at, kind="scan", summary=f"Scan · {n} screenshot{'s' if n != 1 else ''}"))
    if user.last_login_at is not None:
        rows.append(AdminActivityRow(at=user.last_login_at, kind="login", summary="Signed in"))
    rows.sort(key=lambda r: ensure_utc(r.at), reverse=True)
    return rows[:ACTIVITY_LIMIT]


# ── console v2 settings (§4.5, §6.4) ──

def _setting_warning(db: Session, spec: SettingSpec, now: datetime) -> Optional[str]:
    """The live warning lines for the two dangerous switches (§5.5)."""
    if spec.key == "PURCHASE_REQUIRE_JWS":
        n = int(
            db.query(func.count(PurchaseRecord.id))
            .filter(PurchaseRecord.verified == False, PurchaseRecord.created_at >= to_naive_utc(now - timedelta(days=30)))
            .scalar()
            or 0
        )
        return f"{n} purchases in the last 30 d arrived unsigned — those builds will fail to buy until updated."
    if spec.key == "PURGE_SWEEP_ENABLED":
        n = int(db.query(func.count(User.id)).filter(*purge_service.eligible_filter(db, now)).scalar() or 0)
        return f"{n} accounts are purge-eligible right now and will be purged on the next deploy."
    return None


def setting_row(
    db: Session, spec: SettingSpec, *, now: Optional[datetime] = None,
    row: Optional[AppSetting] = None, prefetched: bool = False,
) -> SettingRow:
    """One Settings-screen row: value · default · source (+ the §5.5 warning)."""
    now = now or utcnow()
    resolved = settings_service.resolve(db, spec.key, row=row, prefetched=prefetched)
    return SettingRow(
        key=spec.key,
        label=spec.label,
        group=spec.group,
        type=spec.type,
        value=resolved.value,
        default=resolved.default,
        source=resolved.source,
        tier=spec.tier,
        warning=_setting_warning(db, spec, now),
        updated_at=resolved.updated_at,
        updated_by=resolved.updated_by,
        allowed=list(spec.allowed),
        min=spec.min,
        max=spec.max,
    )


def list_settings(db: Session) -> SettingsResponse:
    """``GET /admin/settings``: every registry key in registry order (one read of the table) + the env block."""
    now = utcnow()
    rows = settings_service.override_rows(db)
    return SettingsResponse(
        items=[setting_row(db, spec, now=now, row=rows.get(spec.key), prefetched=True) for spec in SETTINGS],
        env=env_block(),
    )


PROCESS_STARTED_AT = utcnow()  # import time == boot time: on Railway that is the deploy time


def env_block() -> SettingsEnvBlock:
    """The read-only Integrations · Build · Admin lines (§4.5): presence and public names only.

    Nothing here is a value the console could edit and nothing is a secret — every
    credential collapses to a boolean; ``assert_no_secret_keys`` pins the key names.
    """
    env = os.environ
    return SettingsEnvBlock(
        integrations=EnvIntegrations(
            whoop_configured=whoop_service.is_configured(),
            apns_configured=notification_service.is_configured(),
            apns_topic=settings.APNS_TOPIC,
            apns_sandbox=bool(settings.APNS_USE_SANDBOX),
            sendgrid_configured=bool(env.get("SENDGRID_API_KEY", "").strip()),
            sentry_enabled=bool(env.get("SENTRY_DSN", "").strip()),
        ),
        build=EnvBuild(
            git_sha=env.get("RAILWAY_GIT_COMMIT_SHA") or None,
            git_branch=env.get("RAILWAY_GIT_BRANCH") or None,
            environment=env.get("RAILWAY_ENVIRONMENT_NAME") or None,
            started_at=PROCESS_STARTED_AT,
        ),
        admin=EnvAdmin(
            bootstrap_email=(settings.ADMIN_BOOTSTRAP_EMAIL or "").strip() or None,
            token_ttl_minutes=int(settings.ADMIN_TOKEN_EXPIRE_MINUTES),
            lockout_threshold=int(settings.ADMIN_LOCKOUT_THRESHOLD),
            lockout_minutes=int(settings.ADMIN_LOCKOUT_MINUTES),
            step_up_failures_to_revoke=int(settings.ADMIN_STEP_UP_FAILURES_TO_REVOKE),
        ),
    )
