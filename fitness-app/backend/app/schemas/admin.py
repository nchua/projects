"""
Owner-console (admin) schemas — control-plane spec §13.

Every response here is an explicit allow-list. Nothing uses
``from_attributes`` on ``User``: emails appear where the owner needs them
(list / identity), and ``password_hash``, ``*_encrypted`` columns, device
tokens and reset codes have no field to land in.
"""
from __future__ import annotations

from datetime import date, datetime
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

UserSort = Literal["last_active", "created", "email", "credits"]
SortOrder = Literal["asc", "desc"]


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


class FleetUsers(UTCModel):
    total: int
    deleted: int
    admins: int
    active_7d: int
    active_30d: int
    purge_eligible: int


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
