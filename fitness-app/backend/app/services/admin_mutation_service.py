"""
Admin mutations (control-plane spec §4.5, §6.3-6.4, §7, §8.1). Every
function takes the acting admin, calls ``verify_step_up`` first when it is
destructive tier, changes rows, and writes its audit row with ``audit()``
inside the same transaction — the route commits. Hard purge and the sweep
live in ``purge_service``; the reads in ``admin_read_service``.

To add a mutation: a body schema in ``app/schemas/admin.py`` (``ReasonBody``
/ ``StepUpBody`` / ``OptionalStepUpBody``), a function here following the
pattern above, a route on ``mutation_router`` in ``app/api/admin.py``, and a
``MutationCase`` in ``tests/helpers_admin.MUTATIONS`` (the step-up, audit,
and route-gate tests then cover it).

Bulk routes (console v2 §5.4, §6.4) verify the step-up once, then run
``bulk.per_user`` — one committed transaction per id, a failure recorded and
the loop continued — so every audit row of a batch shares the request id
and a sibling's failure rolls back nothing but its own change.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.admin_auth import protect_account, verify_step_up
from app.core.dependencies import conflict, not_found, unprocessable
from app.core.settings_registry import TIER_DESTRUCTIVE, coerce
from app.core.utils import ensure_utc, to_naive_utc, utcnow
from app.models.admin import AdminAuditLog
from app.models.entitlement import EntitlementSource, Product, UserEntitlement
from app.models.exercise import Exercise
from app.models.user import User
from app.schemas.admin import (
    AdminCampaignImportRequest,
    AdminUserStateResponse,
    ArcPreview,
    BulkPlanChangeRequest,
    BulkPlanChangeResponse,
    BulkStateRequest,
    BulkStateResponse,
    CreditsAdjustResponse,
    EntitlementResponse,
    FamilyBackfillResponse,
    PlanChangeRequest,
    PlanChangeResponse,
    ProductResponse,
    ProductUpsertRequest,
    SettingRow,
    UnresolvedExercise,
)
from app.services import (
    campaign_service,
    campaign_templates,
    entitlement_service,
    settings_service,
)
from app.services.achievement_service import seed_achievement_definitions
from app.services.admin_read_service import entitlement_response, setting_row
from app.services.audit_service import audit, body_hash, snapshot
from app.services.bulk import Skip, per_user
from app.services.entitlement_service import KEY_UNLIMITED, Plan, plan_snapshot
from app.services.exercise_family_service import (
    apply_family_updates,
    ensure_families,
    planned_family_updates,
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

def _prior(db: Session, actor: User, idempotency_key: str, action: str) -> Optional[AdminAuditLog]:
    """The audit row a repeated ``Idempotency-Key`` already wrote for ``action`` (the replay record)."""
    return (
        db.query(AdminAuditLog)
        .filter(
            AdminAuditLog.actor_user_id == actor.id,
            AdminAuditLog.idempotency_key == idempotency_key,
            AdminAuditLog.action == action,
        )
        .first()
    )


def _assert_same_body(prior: AdminAuditLog, digest: str) -> None:
    """422 when a repeated ``Idempotency-Key`` arrives with a different body."""
    if prior.body_sha256 != digest:
        raise unprocessable("Idempotency-Key was already used with a different body")


def _replay(prior: AdminAuditLog, digest: str) -> CreditsAdjustResponse:
    """The stored credits result for a repeated ``Idempotency-Key``."""
    _assert_same_body(prior, digest)
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
    prior = _prior(db, actor, idempotency_key, "credits.adjust")
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
        prior = _prior(db, actor, idempotency_key, "credits.adjust")
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
    return _apply_state(db, actor=actor, user=user, deleted=deleted, reason=reason, request=request)


def _apply_state(
    db: Session, *, actor: User, user: User, deleted: bool, reason: str, request: Optional[Request]
) -> AdminUserStateResponse:
    """The state flip + its audit row, checks already done (shared with the bulk route)."""
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


# ── console v2: change plan (§3.2, §6.4) ──

def plan_step_up_needed(body: PlanChangeRequest) -> bool:
    """Remove Unlimited is destructive; a top-up above the v1 threshold re-verifies too."""
    if body.target == "remove_unlimited":
        return True
    return body.target == "topup" and int(body.credits or 0) > CREDITS_STEP_UP_THRESHOLD


def _active_unlimited_rows(db: Session, user_id: str) -> List[UserEntitlement]:
    return [
        row for row in entitlement_service.active_entitlements(db, user_id, [KEY_UNLIMITED])
        if bool(row.value)
    ]


def _all_admin_granted(rows: Sequence[UserEntitlement]) -> bool:
    """True when every row is an ``admin_grant`` — the only source Change plan may revoke at standard tier."""
    return all(row.source == EntitlementSource.ADMIN_GRANT.value for row in rows)


def _same_expiry(rows: Sequence[UserEntitlement], expires_at: Optional[datetime]) -> bool:
    """True when the newest active row already carries ``expires_at`` (second precision)."""
    current = ensure_utc(rows[0].expires_at) if rows else None
    wanted = ensure_utc(expires_at)
    if current is None or wanted is None:
        return current is wanted
    return current.replace(microsecond=0) == wanted.replace(microsecond=0)


def apply_plan_change(
    db: Session,
    *,
    actor: User,
    user: User,
    body: PlanChangeRequest,
    request: Optional[Request] = None,
    idempotency_key: Optional[str] = None,
    body_sha256: Optional[str] = None,
) -> PlanChangeResponse:
    """One hunter's Change plan, step-up already verified by the caller (flush, no commit).

    ``unlimited`` grants ``scans.unlimited``; on a hunter already unlimited by
    an *admin* grant with a different expiry it revokes + re-grants in this
    transaction (extend / shorten), and the same expiry is ``skipped``. A
    hunter unlimited by purchase or backfill is always ``skipped`` here: only
    ``remove_unlimited`` (destructive tier) may revoke a row the hunter may
    have paid for. ``topup`` adds purchased credits under the balance lock.
    ``remove_unlimited`` revokes every active unlimited row — purchased
    credits are never touched (§3.2). Every applied change writes one
    ``user.plan_change`` row whose before / after are the two ``Plan``
    snapshots; a skip writes none. ``has_unlimited`` is only ever written by
    ``sync_unlimited_flag`` inside ``grant`` / ``revoke``.
    """
    before = entitlement_service.plan_for(db, user.id)
    rows = _active_unlimited_rows(db, user.id)

    if body.target == "unlimited":
        if rows and (_same_expiry(rows, body.expires_at) or not _all_admin_granted(rows)):
            return _skipped(user.id, before)
        for row in rows:  # extend / shorten an admin grant: revoke the old row(s) first
            entitlement_service.revoke(db, row)
        entitlement_service.grant(
            db,
            user_id=user.id,
            key=KEY_UNLIMITED,
            value=True,
            source=EntitlementSource.ADMIN_GRANT,
            granted_by=actor.id,
            reason=body.reason,
            expires_at=to_naive_utc(body.expires_at) if body.expires_at is not None else None,
        )
    elif body.target == "topup":
        balance = entitlement_service.get_or_create_balance(db, user.id, for_update=True, commit=False)
        balance.scan_credits = int(balance.scan_credits) + int(body.credits)
        db.flush()
    else:  # remove_unlimited
        if not rows:
            return _skipped(user.id, before)
        for row in rows:
            entitlement_service.revoke(db, row)

    after = entitlement_service.plan_for(db, user.id)
    row = audit(
        db,
        actor=actor,
        action="user.plan_change",
        target_type="user",
        target_id=user.id,
        before=plan_snapshot(before),
        after=plan_snapshot(after),
        reason=body.reason,
        request=request,
        idempotency_key=idempotency_key,
        body_sha256=body_sha256,
    )
    return PlanChangeResponse(
        user_id=user.id, before=plan_snapshot(before), after=plan_snapshot(after), skipped=False, audit_id=row.id
    )


def _skipped(user_id: str, plan: Plan) -> PlanChangeResponse:
    snap = plan_snapshot(plan)
    return PlanChangeResponse(user_id=user_id, before=snap, after=snap, skipped=True, audit_id=None)


def _replay_plan_change(prior: AdminAuditLog, digest: str) -> PlanChangeResponse:
    """The stored plan-change result for a repeated ``Idempotency-Key``."""
    _assert_same_body(prior, digest)
    return PlanChangeResponse(
        user_id=prior.target_id, before=prior.before, after=prior.after,
        skipped=False, audit_id=prior.id, replayed=True,
    )


def change_plan(
    db: Session,
    *,
    actor: User,
    user: User,
    body: PlanChangeRequest,
    idempotency_key: Optional[str] = None,
    request: Optional[Request] = None,
) -> PlanChangeResponse:
    """``POST /admin/users/{id}/plan``: step-up when the target needs it, then one change.

    With an ``Idempotency-Key`` header the audit row is the replay record, as
    for credits adjust (v1 §7.1): the same key + body returns the stored
    result with ``replayed=True``, a different body is 422, and the partial
    unique index makes a concurrent duplicate replay too. The console sends
    one for top-ups so a retried request cannot credit twice (§3.2).
    """
    digest = None
    if idempotency_key:
        digest = body_hash({"user_id": user.id, **body.model_dump(mode="json", exclude={"password"})})
        prior = _prior(db, actor, idempotency_key, "user.plan_change")
        if prior is not None:
            return _replay_plan_change(prior, digest)
    if plan_step_up_needed(body):
        verify_step_up(db, actor, body.password)
    try:
        return apply_plan_change(
            db, actor=actor, user=user, body=body, request=request,
            idempotency_key=idempotency_key, body_sha256=digest,
        )
    except IntegrityError:
        if not idempotency_key:
            raise
        db.rollback()  # a concurrent request with the same key committed first
        prior = _prior(db, actor, idempotency_key, "user.plan_change")
        if prior is None:
            raise
        return _replay_plan_change(prior, digest)


# ── console v2: bulk (§5.4) — the loop lives in ``app.services.bulk`` ──

def _skip_why(target: str, result: PlanChangeResponse) -> str:
    if target != "unlimited":
        return "not unlimited"
    source = result.before.plan_source
    return "already unlimited" if source == EntitlementSource.ADMIN_GRANT.value else f"already unlimited by {source}"


def bulk_change_plan(
    db: Session, *, actor: User, body: BulkPlanChangeRequest, request: Optional[Request] = None
) -> BulkPlanChangeResponse:
    """``POST /admin/users/plan``: one step-up, then ``apply_plan_change`` per id (§5.2, §5.4)."""
    if plan_step_up_needed(body):
        verify_step_up(db, actor, body.password)

    def step(user: User) -> PlanChangeResponse:
        result = apply_plan_change(db, actor=actor, user=user, body=body, request=request)
        if result.skipped:
            raise Skip(_skip_why(body.target, result))
        return result

    applied, skipped, failed = per_user(db, body.user_ids, step)
    return BulkPlanChangeResponse(applied=applied, skipped=skipped, failed=failed)


def bulk_set_state(
    db: Session, *, actor: User, body: BulkStateRequest, request: Optional[Request] = None
) -> BulkStateResponse:
    """``POST /admin/users/state``: soft-delete or restore many, already-in-state → skipped."""
    verify_step_up(db, actor, body.password)
    deleted = body.action == "delete"

    def step(user: User) -> AdminUserStateResponse:
        protect_account(actor, user)
        if bool(user.is_deleted) == deleted:
            raise Skip("already soft-deleted" if deleted else "not soft-deleted")
        return _apply_state(db, actor=actor, user=user, deleted=deleted, reason=body.reason, request=request)

    applied, skipped, failed = per_user(db, body.user_ids, step)
    return BulkStateResponse(applied=applied, skipped=skipped, failed=failed)


# ── console v2: settings (§4.5, §5.5, §6.4) ──

def update_setting(
    db: Session,
    *,
    actor: User,
    key: str,
    value: Any,
    password: Optional[str],
    reason: str,
    request: Optional[Request] = None,
) -> SettingRow:
    """``PATCH /admin/settings/{key}``: set the console override, or reset it with ``null``.

    404 for a key outside ``SETTINGS_REGISTRY``; 422 when the value fails
    the registry type / bounds; step-up for the destructive tier
    (``PURGE_GRACE_DAYS`` and every switch); 409 when nothing would change.
    Audits ``settings.update`` with ``before = {key: effective, source}`` and
    ``after = {key: new, source: console}`` — ``after = null`` on a reset.
    """
    try:
        spec = settings_service.spec_for(key)
    except KeyError:
        raise not_found(f"Unknown setting: {key}")
    if spec.tier == TIER_DESTRUCTIVE:
        verify_step_up(db, actor, password)
    current = settings_service.resolve(db, key)
    before = {key: current.value, "source": current.source}

    if value is None:
        if not settings_service.reset(db, key):
            raise conflict(f"{key} is not overridden from the console")
        after = None
    else:
        try:
            coerced = coerce(spec, value)
        except ValueError as exc:
            raise unprocessable(str(exc))
        if current.source == settings_service.SOURCE_CONSOLE and current.value == coerced:
            raise conflict(f"{key} is already {coerced!r}")
        settings_service.set_value(db, key, coerced, updated_by=actor.id)
        after = {key: coerced, "source": settings_service.SOURCE_CONSOLE}

    audit(
        db,
        actor=actor,
        action="settings.update",
        target_type="setting",
        target_id=key,
        before=before,
        after=after,
        reason=reason,
        request=request,
    )
    return setting_row(db, spec)
