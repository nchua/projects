"""
Owner-console (admin) schemas — control-plane spec §13.

Every response here is an explicit allow-list. Nothing uses
``from_attributes`` on ``User``: emails appear where the owner needs them
(list / identity), and ``password_hash``, ``*_encrypted`` columns, device
tokens and reset codes have no field to land in.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import EmailStr, Field, field_validator, model_validator

from app.schemas.base import UTCModel
from app.schemas.campaign import (
    ArcResponse,
    CampaignImportRequest,
    CampaignImportResponse,
    PhaseIn,
)
from app.schemas.progress import UserProgressResponse
from app.services.campaign_templates import TEMPLATE_NAMES
from app.services.entitlement_service import ENTITLEMENT_KEYS, validate_grant

# ``created`` is the v1 spelling of ``created_at``; both stay (console v2 §6.2).
UserSort = Literal[
    "last_active", "created", "created_at", "email", "credits",
    "plan", "status", "scans_4wk", "level", "session_count",
]
SortOrder = Literal["asc", "desc"]
PlanName = Literal["unlimited", "override", "credits", "free"]
StatusName = Literal["active", "inactive", "deleted", "purge_eligible"]
LastActiveKind = Literal["workout", "scan", "login"]


# ── session / identity ──────────────────────────────────────────────────────


class AdminSessionRequest(UTCModel):
    """``POST /admin/session`` body."""

    email: EmailStr
    password: str = Field(min_length=1)


class AdminSessionResponse(UTCModel):
    """A short-lived admin token (no refresh token exists)."""

    admin_token: str
    expires_at: datetime


class AdminMeResponse(UTCModel):
    """Who the token belongs to and when it dies."""

    user_id: str
    token_expires_at: datetime


# ── user list ───────────────────────────────────────────────────────────────


class AdminUserRow(UTCModel):
    """One row of the Hunters table."""

    id: str
    email: str
    username: Optional[str] = None
    created_at: datetime
    is_deleted: bool
    deleted_at: Optional[datetime] = None
    is_admin: bool
    level: Optional[int] = None
    rank: Optional[str] = None
    last_workout_date: Optional[date] = None
    session_count: int = 0
    scan_credits: Optional[int] = None
    has_unlimited: bool = False
    # ── console v2 §6.2: the plan and status models, derived server-side ──
    plan: PlanName
    plan_source: Optional[str] = None
    plan_expires_at: Optional[datetime] = None
    purchased_credits: int = 0
    free_monthly: int
    status: StatusName
    last_active: Optional[date] = None
    last_active_kind: Optional[LastActiveKind] = None
    scans_4wk: int = 0
    override_keys: List[str] = Field(default_factory=list)  # the row plan chip lists them (v2 §7.4 v2.3)


class AdminUserListResponse(UTCModel):
    items: List[AdminUserRow]
    total: int


# ── user detail blocks ──────────────────────────────────────────────────────


class AdminUserIdentity(UTCModel):
    """The account row, allow-listed."""

    id: str
    email: str
    username: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_deleted: bool
    deleted_at: Optional[datetime] = None
    purge_eligible_at: Optional[datetime] = None
    is_admin: bool
    token_version: int
    admin_failed_logins: int = 0
    admin_locked_until: Optional[datetime] = None


class AdminProfile(UTCModel):
    """``user_profiles`` — read-only for the console."""

    age: Optional[int] = None
    sex: Optional[str] = None
    bodyweight_lb: Optional[float] = None
    height_inches: Optional[float] = None
    training_experience: Optional[str] = None
    preferred_unit: Optional[str] = None
    e1rm_formula: Optional[str] = None
    injury_notes: Optional[str] = None
    run_hr_cap_bpm: Optional[int] = None


class AdminPurchaseRow(UTCModel):
    id: str
    product_id: str
    transaction_id: str
    credits_added: int
    purchase_type: str
    created_at: datetime
    # App Store JWS verification (§6.5): False for a bare client claim.
    verified: bool = False
    environment: Optional[str] = None


class AdminBalanceBlock(UTCModel):
    """The balance row (``exists=False`` for a user who never scanned) + receipts."""

    exists: bool
    scan_credits: Optional[int] = None
    has_unlimited: bool = False
    free_scans_reset_at: Optional[datetime] = None
    purchases: List[AdminPurchaseRow] = Field(default_factory=list)


class EntitlementResponse(UTCModel):
    """One ``user_entitlements`` row (history included; ``active`` is derived)."""

    id: str
    user_id: str
    key: str
    value: Any
    source: str
    granted_by: Optional[str] = None
    purchase_record_id: Optional[str] = None
    reason: Optional[str] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    active: bool


class AdminEffectiveLimits(UTCModel):
    """Overrides overlaid on the global defaults (``effective_limits``)."""

    daily_limit: int
    cooldown_seconds: int
    free_monthly: int
    defaults: Dict[str, int]


class AdminCampaignSummary(UTCModel):
    """The active campaign, summarized (arcs/templates stay on ``GET /campaign``)."""

    id: str
    name: str
    goal: Optional[str] = None
    start_date: str
    end_date: str
    status: str
    source: str
    arcs: int
    current_arc_index: Optional[int] = None
    week_in_arc: Optional[int] = None
    campaign_week: Optional[int] = None
    deload_week: bool = False
    week_start: str
    week_target_miles: Optional[float] = None
    next_planned_hunt: Optional[str] = None
    created_at: Optional[str] = None


class AdminWhoopStatus(UTCModel):
    """WHOOP freshness — never the tokens."""

    connected: bool
    last_synced_at: Optional[datetime] = None
    token_expires_at: Optional[datetime] = None
    scope: Optional[str] = None


class AdminIntegrations(UTCModel):
    whoop: AdminWhoopStatus
    active_device_tokens: int
    latest_daily_activity_date: Optional[date] = None
    daily_activity_sources_30d: List[str] = Field(default_factory=list)


class AdminDataHealth(UTCModel):
    sessions_total: int
    sessions_soft_deleted: int
    sessions_missing_local_date: int
    custom_exercises: int
    custom_exercises_without_family: int
    bodyweight_entries: int
    last_bodyweight_date: Optional[date] = None
    prs_total: int
    goals_by_status: Dict[str, int] = Field(default_factory=dict)
    gates_by_status: Dict[str, int] = Field(default_factory=dict)
    achievements_unlocked: int


class AdminPreviewHunt(UTCModel):
    id: str
    date: str
    type: str
    title: str
    status: str
    location_tag: Optional[str] = None
    system_line: str


class AdminPreviewLoad(UTCModel):
    as_of: str
    run_acwr: Optional[float] = None
    total_acwr: Optional[float] = None
    band: str
    miles_7d: float
    miles_plan_7d: Optional[float] = None
    longest_run_7d: float
    flags: List[str] = Field(default_factory=list)


class AdminPreviewCondition(UTCModel):
    score: int
    band: str
    generated_at: str


class AdminPreviewProgress(UTCModel):
    level: int
    rank: str
    total_xp: int
    xp_to_next_level: int
    current_streak: int


class AdminPreviewBalance(UTCModel):
    scan_credits: int
    has_unlimited: bool


class AdminPreview(UTCModel):
    """What the Status tab shows the user today, composed server-side (§9.2)."""

    today: date
    hunt: Optional[AdminPreviewHunt] = None
    load: AdminPreviewLoad
    condition: AdminPreviewCondition
    progress: AdminPreviewProgress
    scan_balance: AdminPreviewBalance


# ── console v2 detail blocks (§6.3) ─────────────────────────────────────────


class AdminPlanSnapshot(UTCModel):
    """``entitlement_service.Plan`` on the wire — also the audit before/after shape."""

    plan: PlanName
    plan_source: Optional[str] = None
    expires_at: Optional[datetime] = None
    scan_credits: Optional[int] = None
    purchased_credits: int = 0
    free_monthly: int
    override_keys: List[str] = Field(default_factory=list)


class AdminPlanChange(UTCModel):
    """The newest plan-affecting audit row (Plan card: "last change")."""

    at: datetime
    actor: Optional[str] = None
    action: str
    reason: Optional[str] = None
    audit_id: str


class AdminPlanBlock(AdminPlanSnapshot):
    last_change: Optional[AdminPlanChange] = None


class AdminAccountBlock(UTCModel):
    status: StatusName
    purge_at: Optional[datetime] = None
    last_active: Optional[date] = None
    last_active_kind: Optional[LastActiveKind] = None
    last_login_at: Optional[datetime] = None
    token_version: int
    admin_locked_until: Optional[datetime] = None


class AdminScansBlock(UTCModel):
    scan_credits: Optional[int] = None
    purchased_credits: int = 0
    free_monthly: int
    free_scans_reset_at: Optional[datetime] = None
    used_7d: int = 0
    used_4wk: int = 0
    today_count: int = 0
    daily_limit: int
    cooldown_seconds: int


class AdminActivityRow(UTCModel):
    """One line of the merged Activity list: audit rows, sessions, scans, the last login."""

    at: datetime
    kind: Literal["audit", "session", "scan", "login"]
    summary: str
    actor: Optional[str] = None
    audit_id: Optional[str] = None


# ── audit ───────────────────────────────────────────────────────────────────


class AuditEntry(UTCModel):
    id: str
    actor_user_id: Optional[str] = None
    action: str
    target_type: str
    target_id: Optional[str] = None
    before: Optional[Any] = None
    after: Optional[Any] = None
    reason: Optional[str] = None
    request_id: Optional[str] = None
    ip: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: datetime


class AuditListResponse(UTCModel):
    items: List[AuditEntry]
    total: int
    actions: List[str] = Field(default_factory=list)  # the registry (audit_service.AUDIT_ACTIONS) — the filter select reads it


# ── products ────────────────────────────────────────────────────────────────


class ProductResponse(UTCModel):
    id: str
    kind: str
    credits: int
    entitlement_key: Optional[str] = None
    display_name: str
    active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime
    sold: int = 0  # purchase_records citing this product (§4.6)
    sold_verified: int = 0  # …of which carry a verified receipt


# ── usage (spec §9.3) ───────────────────────────────────────────────────────


class WeekSessions(UTCModel):
    week: str  # ISO week label, e.g. "2026-W36"
    strength: int = 0
    cardio: int = 0
    other: int = 0
    miles: float = 0.0


class SessionSource(UTCModel):
    origin: str  # "hk" | "app"
    hr_source: str  # column value or "none"
    sessions: int


class TopExercise(UTCModel):
    name: str
    sessions: int
    sets: int
    best_e1rm: Optional[float] = None
    sets_with_rpe: int
    sets_with_hr: int


class LiftWeekPoint(UTCModel):
    week_start: date
    best_e1rm: Optional[float] = None
    sets: int


class BigThreeSeries(UTCModel):
    lift: str
    weeks_with_data: int
    series: List[LiftWeekPoint] = Field(default_factory=list)


class SessionMeta(UTCModel):
    sessions: int
    avg_duration_minutes: Optional[float] = None
    named: int
    with_session_rpe: int
    with_notes: int
    with_avg_hr: int
    with_strain: int
    with_splits: int


class ActivityCoverage(UTCModel):
    source: str
    days: int
    steps: int
    sleep: int
    hrv: int
    resting_hr: int
    recovery: int
    strain: int


class UserIntegrationsUsage(UTCModel):
    whoop_connected: bool
    whoop_last_synced_at: Optional[datetime] = None
    whoop_token_expires_at: Optional[datetime] = None
    whoop_scope: Optional[str] = None
    active_device_tokens: int
    goals_by_status: Dict[str, int] = Field(default_factory=dict)
    bodyweight_entries: int
    last_bodyweight_date: Optional[date] = None
    prs_last_12_weeks: int
    achievements_unlocked: int
    scan_credits: Optional[int] = None
    has_unlimited: bool = False


class WeekScans(UTCModel):
    week: str
    scans: int
    screenshots: int


class ScanUsage(UTCModel):
    weeks: int
    scans: int
    screenshots: int
    by_week: List[WeekScans] = Field(default_factory=list)


class RunRow(UTCModel):
    local_date: date
    activity_type: Optional[str] = None
    miles: float
    duration_minutes: Optional[int] = None
    pace_min_per_mile: Optional[float] = None
    avg_heart_rate: Optional[int] = None
    has_splits: bool


class UserUsageResponse(UTCModel):
    user_id: str
    weeks: int
    generated_at: datetime
    sessions_by_week: List[WeekSessions]
    kinds: Dict[str, int]
    sources: List[SessionSource]
    top_exercises: List[TopExercise]
    big_three: List[BigThreeSeries]
    session_meta: SessionMeta
    gates_by_status: Dict[str, int]
    activity_coverage: List[ActivityCoverage]
    latest_daily_activity_date: Optional[date] = None
    integrations: UserIntegrationsUsage
    scans: ScanUsage
    runs: List[RunRow]


class PlanCounts(UTCModel):
    """Live hunters by plan (§3.1) — the Overview's Unlimited / Credits tiles equal the filtered list totals."""

    unlimited: int = 0
    override: int = 0
    credits: int = 0
    free: int = 0


class FleetUsers(UTCModel):
    total: int
    deleted: int
    admins: int
    active_7d: int
    active_30d: int
    purge_eligible: int
    active: int = 0  # status counts by the §3.3 twin: the tiles equal their filtered lists (v2.4)
    inactive: int = 0
    new_7d: int = 0  # joined in the last 7 days, not deleted (the Hunters joined_days=7 chip)
    by_plan: PlanCounts = Field(default_factory=PlanCounts)


class FleetWeekSessions(UTCModel):
    week: str
    sessions: int
    active_users: int


class FleetBalances(UTCModel):
    rows: int
    unlimited_count: int
    credits_total: int


class FleetIntegrations(UTCModel):
    whoop_connections: int
    active_device_tokens: int


class FleetExercises(UTCModel):
    total: int
    custom: int
    without_family: int


class UnlimitedDriftRow(UTCModel):
    """A balance whose cached flag disagrees with the derived entitlement (§6.2)."""

    user_id: str
    has_unlimited: bool
    derived: bool


class PlanSourceCounts(UTCModel):
    """Unlimited hunters by where the grant came from (§3.1) — the Overview tile's split."""

    purchase: int = 0
    admin_grant: int = 0
    backfill: int = 0


class ScansByPlan(UTCModel):
    """Scans in the last 28 days by the scanning hunter's plan (§4.2 Scans tile)."""

    free: int = 0
    credits: int = 0
    unlimited: int = 0
    override: int = 0


class FleetUsageResponse(UTCModel):
    generated_at: datetime
    weeks: int
    users: FleetUsers
    sessions_by_week: List[FleetWeekSessions]
    scans_by_week: List[WeekScans]
    balances: FleetBalances
    integrations: FleetIntegrations
    exercises: FleetExercises
    unlimited_flag_drift: List[UnlimitedDriftRow]
    by_plan_source: PlanSourceCounts = Field(default_factory=PlanSourceCounts)
    purchased_credits_total: int = 0  # outstanding purchased credits across every live hunter
    scans_4wk_by_plan: ScansByPlan = Field(default_factory=ScansByPlan)


# ── user detail ─────────────────────────────────────────────────────────────


class AdminUserDetailResponse(UTCModel):
    """``GET /admin/users/{id}`` — every card of the Hunter detail (§10.3)."""

    user: AdminUserIdentity
    profile: Optional[AdminProfile] = None
    progress: UserProgressResponse
    balance: AdminBalanceBlock
    entitlements: List[EntitlementResponse]
    effective_limits: AdminEffectiveLimits
    campaign: Optional[AdminCampaignSummary] = None
    integrations: AdminIntegrations
    data_health: AdminDataHealth
    preview: AdminPreview
    recent_audit: List[AuditEntry]
    usage: UserUsageResponse
    # ── console v2 §6.3 ──
    plan: AdminPlanBlock
    account: AdminAccountBlock
    scans: AdminScansBlock
    activity: List[AdminActivityRow] = Field(default_factory=list)


# ── mutations (spec §4.5, §7, §8, §13) ───────────────────────────────────────

# Every request that changes state carries a ``reason`` (spec §5); the
# destructive tier adds ``password`` (``StepUpBody``). Routes whose tier
# depends on the body (large credit deltas, ``replace``, ``dry_run=false``,
# ``active=false``) take ``OptionalStepUpBody`` and the service decides.
FORCE_REASON_MIN_LENGTH = 10


class ReasonBody(UTCModel):
    reason: str = Field(min_length=3, max_length=500)


class StepUpBody(ReasonBody):
    """Marks the destructive tier: the admin re-enters their password."""

    password: str = Field(min_length=1)


class OptionalStepUpBody(ReasonBody):
    """A body whose tier depends on its content; the service asks for ``password`` when needed."""

    password: Optional[str] = None


class DryRunBody(OptionalStepUpBody):
    """Dry run by default; ``dry_run=false`` is the destructive apply."""

    dry_run: bool = True


class CreditsAdjustRequest(OptionalStepUpBody):
    """``POST /admin/users/{id}/credits`` (+ ``Idempotency-Key`` header)."""

    delta: int

    @field_validator("delta")
    @classmethod
    def _non_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("delta must not be 0")
        return value


class CreditsAdjustResponse(UTCModel):
    scan_credits_before: int
    scan_credits_after: int
    audit_id: str
    replayed: bool = False


class EntitlementGrantRequest(ReasonBody):
    key: str = Field(min_length=1, max_length=64)
    value: Any
    expires_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _registered_key_and_typed_value(self) -> "EntitlementGrantRequest":
        validate_grant(self.key, self.value)  # ValueError → 422
        return self


class AdminUserStateResponse(UTCModel):
    """Soft-delete / restore result."""

    id: str
    is_deleted: bool
    deleted_at: Optional[datetime] = None


class PurgeRequest(StepUpBody):
    confirm_email: str = Field(min_length=3)
    force: bool = False

    @model_validator(mode="after")
    def _forced_purge_needs_a_real_reason(self) -> "PurgeRequest":
        if self.force and len(self.reason.strip()) < FORCE_REASON_MIN_LENGTH:
            raise ValueError(f"a forced purge needs a reason of at least {FORCE_REASON_MIN_LENGTH} characters")
        return self


class PurgeResponse(UTCModel):
    user_id: str
    deleted_at: Optional[datetime] = None
    tables: Dict[str, int]
    audit_id: str


class PurgeEligibleRow(UTCModel):
    user_id: str
    deleted_at: datetime
    days_deleted: int


class PurgeSweepRequest(DryRunBody):
    """``POST /admin/maintenance/purge-eligible``."""


class PurgeSweepResponse(UTCModel):
    dry_run: bool
    eligible: List[PurgeEligibleRow]
    purged: List[PurgeResponse] = Field(default_factory=list)


class ProductUpsertRequest(OptionalStepUpBody):
    """``POST /admin/products`` creates, ``PATCH /admin/products/{id}`` edits (id immutable)."""

    id: str = Field(min_length=1, max_length=200)
    kind: Literal["consumable", "non_consumable", "subscription"]
    credits: int = Field(0, ge=0)
    entitlement_key: Optional[str] = None
    display_name: str = Field(min_length=1, max_length=120)
    active: bool = True
    sort_order: int = 0

    @field_validator("entitlement_key")
    @classmethod
    def _registered_key(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in ENTITLEMENT_KEYS:
            raise ValueError(f"unknown entitlement key: {value}")
        return value


class FamilyBackfillRequest(DryRunBody):
    """``POST /admin/maintenance/exercise-families``."""


class UnresolvedExercise(UTCModel):
    name: str
    is_custom: bool
    user_id: Optional[str] = None


class FamilyBackfillResponse(UTCModel):
    dry_run: bool
    families_changed: int
    exercises_updated: int
    assigned: int
    total: int
    unresolved: List[UnresolvedExercise] = Field(default_factory=list)


class SeedAchievementsResponse(UTCModel):
    seeded: int


class AdminCampaignImportRequest(CampaignImportRequest, OptionalStepUpBody):
    """``POST /admin/users/{id}/campaign/import``: pasted ``phases`` XOR a server ``template``."""

    phases: Optional[List[PhaseIn]] = Field(None, min_length=1)
    template: Optional[str] = None
    dry_run: bool = False

    @field_validator("template")
    @classmethod
    def _known_template(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in TEMPLATE_NAMES:
            raise ValueError(f"unknown template: {value} (known: {', '.join(TEMPLATE_NAMES)})")
        return value

    @model_validator(mode="after")
    def _phases_xor_template(self) -> "AdminCampaignImportRequest":
        if (self.phases is None) == (self.template is None):
            raise ValueError("send exactly one of phases or template")
        return self


class ArcPreview(UTCModel):
    """One arc as a dry run would create it."""

    index: int
    name: str
    weeks: int
    run_miles_min: Optional[float] = None
    run_miles_max: Optional[float] = None
    long_run_miles: Optional[float] = None
    templates: int
    notes: Optional[str] = None


class AdminCampaignImportResponse(CampaignImportResponse):
    """The public import response plus the admin facts.

    A dry run creates no campaign, so the ``CampaignResponse`` identity
    fields relax to optional and ``arcs_preview`` carries the plan instead.
    """

    id: Optional[str] = None
    name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    arcs: List[ArcResponse] = Field(default_factory=list)
    week_start: Optional[str] = None
    dry_run: bool = False
    retired_campaign_id: Optional[str] = None
    planned_hunts_deleted: int = 0
    arcs_preview: Optional[List[ArcPreview]] = None


# ── console v2 mutations (§6.4) ─────────────────────────────────────────────

PlanTarget = Literal["unlimited", "topup", "remove_unlimited"]
BULK_MAX = 100


class PlanChangeRequest(OptionalStepUpBody):
    """``POST /admin/users/{id}/plan``; the bulk request extends it with ``user_ids``."""

    target: PlanTarget
    expires_at: Optional[datetime] = None   # unlimited only; None = never
    credits: Optional[int] = None           # topup only; ≥ 1

    @model_validator(mode="after")
    def _fields_match_target(self) -> "PlanChangeRequest":
        if self.target == "topup":
            if self.credits is None or self.credits < 1:
                raise ValueError("topup needs credits ≥ 1")
        elif self.credits is not None:
            raise ValueError("credits only applies to topup")
        if self.target != "unlimited" and self.expires_at is not None:
            raise ValueError("expires_at only applies to unlimited")
        if self.expires_at is not None and self.expires_at <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        return self


class PlanChangeResponse(UTCModel):
    user_id: str
    before: AdminPlanSnapshot
    after: AdminPlanSnapshot
    skipped: bool = False
    audit_id: Optional[str] = None  # None when skipped (no audit row)
    replayed: bool = False          # a repeated Idempotency-Key answered from the audit row


class BulkSkipped(UTCModel):
    user_id: str
    why: str


class BulkFailed(UTCModel):
    user_id: str
    error: str


def _user_ids_field() -> Any:
    return Field(min_length=1, max_length=BULK_MAX)


class BulkPlanChangeRequest(PlanChangeRequest):
    """``POST /admin/users/plan`` — one transaction per user."""

    user_ids: List[str] = _user_ids_field()


class BulkPlanChangeResponse(UTCModel):
    applied: List[PlanChangeResponse] = Field(default_factory=list)
    skipped: List[BulkSkipped] = Field(default_factory=list)
    failed: List[BulkFailed] = Field(default_factory=list)


class BulkStateRequest(StepUpBody):
    """``POST /admin/users/state`` — soft-delete or restore many."""

    user_ids: List[str] = _user_ids_field()
    action: Literal["delete", "restore"]


class BulkStateResponse(UTCModel):
    applied: List[AdminUserStateResponse] = Field(default_factory=list)
    skipped: List[BulkSkipped] = Field(default_factory=list)
    failed: List[BulkFailed] = Field(default_factory=list)


class BulkPurgeRequest(DryRunBody):
    """``POST /admin/users/purge`` — dry run lists the tables; apply needs password + the typed count."""

    user_ids: List[str] = _user_ids_field()
    confirm_count: Optional[int] = None


class BulkPurgePreviewRow(UTCModel):
    user_id: str
    tables: Dict[str, int]


class BulkPurgeResponse(UTCModel):
    """One shape for both legs: ``preview`` on a dry run, the three groups on apply."""

    dry_run: bool
    preview: List[BulkPurgePreviewRow] = Field(default_factory=list)
    applied: List[PurgeResponse] = Field(default_factory=list)
    skipped: List[BulkSkipped] = Field(default_factory=list)
    failed: List[BulkFailed] = Field(default_factory=list)


# ── console v2 settings (§4.5, §6.4, §6.5) ──────────────────────────────────


class SettingRow(UTCModel):
    key: str
    label: str
    group: Literal["scanner", "accounts", "switches"]
    type: Literal["int", "seconds", "bool", "csv"]
    value: Any
    default: Any
    source: Literal["console", "env", "code"]
    tier: Literal["standard", "destructive"]
    warning: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
    allowed: List[str] = Field(default_factory=list)  # csv rows: the registry's allow-list (the drawer validates from it)
    min: Optional[int] = None  # int / seconds rows: the registry bounds
    max: Optional[int] = None


class SettingUpdateRequest(OptionalStepUpBody):
    """``PATCH /admin/settings/{key}``: ``value`` null (or absent) resets to the env / code value."""

    value: Optional[Any] = None


class EnvIntegrations(UTCModel):
    """Which integrations the deploy has configured — booleans and public names only, never a value."""

    whoop_configured: bool
    apns_configured: bool
    apns_topic: str
    apns_sandbox: bool
    sendgrid_configured: bool
    sentry_enabled: bool


class EnvBuild(UTCModel):
    """What is running: the Railway git facts and when this process started (the deploy time)."""

    git_sha: Optional[str] = None
    git_branch: Optional[str] = None
    environment: Optional[str] = None
    started_at: datetime


class EnvAdmin(UTCModel):
    """The admin-session policy — env-only on purpose (§4.5, §7.3)."""

    bootstrap_email: Optional[str] = None
    token_ttl_minutes: int
    lockout_threshold: int
    lockout_minutes: int
    step_up_failures_to_revoke: int


class SettingsEnvBlock(UTCModel):
    """The read-only lines at the bottom of Settings (§4.5): deploy-time facts the console cannot edit."""

    integrations: EnvIntegrations
    build: EnvBuild
    admin: EnvAdmin


class SettingsResponse(UTCModel):
    """``GET /admin/settings``: every editable row in registry order plus the env block."""

    items: List[SettingRow]
    env: SettingsEnvBlock
