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
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.admin_auth import protect_account, verify_step_up
from app.core.dependencies import conflict, not_found, unprocessable
from app.core.utils import to_naive_utc, utcnow
from app.models.admin import AdminAuditLog
from app.models.entitlement import EntitlementSource, Product, UserEntitlement
from app.models.exercise import Exercise
from app.models.user import User
from app.schemas.admin import (
    AdminCampaignImportRequest,
    AdminUserStateResponse,
    ArcPreview,
    CreditsAdjustResponse,
    EntitlementResponse,
    FamilyBackfillResponse,
    ProductResponse,
    ProductUpsertRequest,
    UnresolvedExercise,
)
from app.services import (
    campaign_service,
    campaign_templates,
    entitlement_service,
)
from app.services.achievement_service import seed_achievement_definitions
from app.services.admin_read_service import entitlement_response
from app.services.audit_service import audit, body_hash, snapshot
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
