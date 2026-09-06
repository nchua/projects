"""
Owner console API — every ``/admin/*`` route (control-plane spec §7-§9, §13).

Three routers, all mounted under ``/admin`` and hidden from OpenAPI:

* ``session_router`` — ``POST /admin/session`` only. It runs *before*
  ``require_admin`` (there is no token yet), so it is rate-limited with the
  login policy and stamps ``request.state.audit_ip`` itself so the
  ``session.create`` audit row carries the caller's IP.
* ``router`` — the reads, with ``require_admin`` attached at the router
  level so no handler can forget it. Handlers take ``Depends(get_read_only_db)``:
  the same request session, marked read-only on Postgres so an accidental
  write fails loudly (spec §9.3).
* ``mutation_router`` — the writes, same router-level ``require_admin`` but
  plain ``get_db``. Each handler calls one service function (which
  re-verifies the password on the destructive tier and writes the audit
  row) and then commits, so the change and its audit row land together.
  There is no ``DELETE`` anywhere under ``/admin``: products deactivate,
  accounts soft-delete, and purge is an explicit ``POST``.

``Cache-Control: no-store`` (and ``X-Frame-Options: DENY``) on every
``/admin/*`` response is added by ``AdminResponseHeadersMiddleware`` in
``main.py`` so error responses carry it too.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.admin_auth import require_admin
from app.core.database import get_db, mark_read_only
from app.core.dependencies import not_found
from app.core.rate_limit import LOGIN_RATE_LIMIT, client_ip, limiter
from app.models.user import User
from app.schemas.admin import (
    AdminCampaignImportRequest,
    AdminCampaignImportResponse,
    AdminMeResponse,
    AdminSessionRequest,
    AdminSessionResponse,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserStateResponse,
    AuditListResponse,
    CreditsAdjustRequest,
    CreditsAdjustResponse,
    EntitlementGrantRequest,
    EntitlementResponse,
    FamilyBackfillRequest,
    FamilyBackfillResponse,
    FleetUsageResponse,
    ProductResponse,
    ProductUpsertRequest,
    PurgeRequest,
    PurgeResponse,
    PurgeSweepRequest,
    PurgeSweepResponse,
    ReasonBody,
    SeedAchievementsResponse,
    SortOrder,
    StepUpBody,
    UserSort,
    UserUsageResponse,
)
from app.services import (
    admin_mutation_service,
    admin_read_service,
    admin_session_service,
    admin_usage_service,
    purge_service,
)

session_router = APIRouter()
router = APIRouter(dependencies=[Depends(require_admin)])
mutation_router = APIRouter(dependencies=[Depends(require_admin)])


def get_read_only_db(db: Session = Depends(get_db)) -> Session:
    """The request session, marked read-only where the dialect supports it."""
    mark_read_only(db)
    return db


def get_target_user(user_id: str, db: Session = Depends(get_db)) -> User:
    """The ``{user_id}`` path target (deleted accounts included), or 404."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise not_found("User not found")
    return user


# ── session (no admin token yet) ────────────────────────────────────────────

@session_router.post("/session", response_model=AdminSessionResponse)
@limiter.limit(LOGIN_RATE_LIMIT)
async def create_session(
    request: Request, body: AdminSessionRequest, db: Session = Depends(get_db)
):
    """Mint a 15-minute admin token (spec §4.2). 401 / 403 / 423 per the service."""
    request.state.audit_ip = client_ip(request)
    token, expires_at = admin_session_service.mint_admin_session(
        db, email=body.email, password=body.password, request=request
    )
    return AdminSessionResponse(admin_token=token, expires_at=expires_at)


# ── reads ───────────────────────────────────────────────────────────────────

@router.get("/me", response_model=AdminMeResponse)
async def me(request: Request, actor: User = Depends(require_admin)):
    """Who the admin token belongs to and when it expires."""
    return AdminMeResponse(
        user_id=actor.id, token_expires_at=request.state.admin_token_expires_at
    )


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    q: Optional[str] = Query(None, max_length=120, description="email / username substring"),
    deleted: Optional[bool] = Query(None),
    unlimited: Optional[bool] = Query(None),
    active_days: Optional[int] = Query(None, ge=1, le=365),
    sort: UserSort = Query("last_active"),
    order: SortOrder = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_only_db),
):
    """The Hunters table (spec §9.1): filters, sort, offset paging."""
    items, total = admin_read_service.list_users(
        db,
        q=q,
        deleted=deleted,
        unlimited=unlimited,
        active_days=active_days,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return AdminUserListResponse(items=items, total=total)


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
async def get_user(
    user: User = Depends(get_target_user), db: Session = Depends(get_read_only_db)
):
    """Every card of the Hunter detail (spec §9.1 / §10.3)."""
    return admin_read_service.get_user_detail(db, user)


@router.get("/users/{user_id}/usage", response_model=UserUsageResponse)
async def get_user_usage(
    user: User = Depends(get_target_user),
    weeks: int = Query(20, ge=1, le=104),
    db: Session = Depends(get_read_only_db),
):
    """Per-user usage block (spec §9.3)."""
    return admin_usage_service.user_usage(db, user.id, weeks=weeks)


@router.get("/usage", response_model=FleetUsageResponse)
async def get_fleet_usage(
    weeks: int = Query(20, ge=1, le=104), db: Session = Depends(get_read_only_db)
):
    """Fleet rollup behind the Overview screen (spec §9.3)."""
    return admin_usage_service.fleet_usage(db, weeks=weeks)


@router.get("/audit", response_model=AuditListResponse)
async def list_audit(
    target_type: Optional[str] = Query(None, max_length=40),
    target_id: Optional[str] = Query(None, max_length=64),
    actor_user_id: Optional[str] = Query(None, max_length=64),
    action: Optional[str] = Query(None, max_length=64),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_only_db),
):
    """Newest-first page of the append-only audit log (spec §5)."""
    items, total = admin_read_service.list_audit(
        db,
        target_type=target_type,
        target_id=target_id,
        actor_user_id=actor_user_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    return AuditListResponse(items=items, total=total)


@router.get("/products", response_model=List[ProductResponse])
async def list_products(db: Session = Depends(get_read_only_db)):
    """The product catalog in display order (active and inactive)."""
    return admin_read_service.list_products(db)


# ── mutations (spec §7, §8, §13) ────────────────────────────────────────────

@mutation_router.post("/users/{user_id}/credits", response_model=CreditsAdjustResponse)
async def adjust_credits(
    request: Request,
    body: CreditsAdjustRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=128),
    user: User = Depends(get_target_user),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CreditsAdjustResponse:
    """Add ``delta`` credits (spec §7.1). ``Idempotency-Key`` is required (400 without)."""
    if not idempotency_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key header required")
    result = admin_mutation_service.adjust_credits(
        db,
        actor=actor,
        user=user,
        delta=body.delta,
        reason=body.reason,
        password=body.password,
        idempotency_key=idempotency_key,
        request=request,
    )
    db.commit()
    return result


@mutation_router.post(
    "/users/{user_id}/entitlements",
    response_model=EntitlementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_entitlement(
    request: Request,
    body: EntitlementGrantRequest,
    user: User = Depends(get_target_user),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EntitlementResponse:
    """Grant a keyed right or limit (spec §6.3); ``scans.unlimited`` syncs the cached flag."""
    result = admin_mutation_service.grant_entitlement(
        db,
        actor=actor,
        user=user,
        key=body.key,
        value=body.value,
        expires_at=body.expires_at,
        reason=body.reason,
        request=request,
    )
    db.commit()
    return result


@mutation_router.post(
    "/users/{user_id}/entitlements/{entitlement_id}/revoke", response_model=EntitlementResponse
)
async def revoke_entitlement(
    request: Request,
    entitlement_id: str,
    body: StepUpBody,
    user: User = Depends(get_target_user),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EntitlementResponse:
    """Revoke one entitlement row (destructive tier); survives Restore Purchases."""
    result = admin_mutation_service.revoke_entitlement(
        db,
        actor=actor,
        user=user,
        entitlement_id=entitlement_id,
        password=body.password,
        reason=body.reason,
        request=request,
    )
    db.commit()
    return result


@mutation_router.post(
    "/users/{user_id}/campaign/import",
    response_model=AdminCampaignImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_campaign(
    request: Request,
    response: Response,
    body: AdminCampaignImportRequest,
    user: User = Depends(get_target_user),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Import a plan for the target user from pasted phases or a template (spec §7.2).

    201 with the campaign; a dry run parses only and answers 200 with ``arcs_preview``.
    """
    result = admin_mutation_service.import_campaign_for_user(db, actor=actor, user=user, body=body, request=request)
    db.commit()
    if body.dry_run:
        response.status_code = status.HTTP_200_OK
    return result


@mutation_router.post("/users/{user_id}/delete", response_model=AdminUserStateResponse)
async def soft_delete_user(
    request: Request,
    body: StepUpBody,
    user: User = Depends(get_target_user),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserStateResponse:
    """Soft-delete (spec §8.1): the user's next request is a 401, login a 403."""
    result = admin_mutation_service.soft_delete_user(
        db, actor=actor, user=user, password=body.password, reason=body.reason, request=request
    )
    db.commit()
    return result


@mutation_router.post("/users/{user_id}/restore", response_model=AdminUserStateResponse)
async def restore_user(
    request: Request,
    body: StepUpBody,
    user: User = Depends(get_target_user),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserStateResponse:
    """Undo a soft-delete and bump ``token_version`` (spec §8.1)."""
    result = admin_mutation_service.restore_user(
        db, actor=actor, user=user, password=body.password, reason=body.reason, request=request
    )
    db.commit()
    return result


@mutation_router.post("/users/{user_id}/purge", response_model=PurgeResponse)
async def purge_user(
    request: Request,
    body: PurgeRequest,
    user: User = Depends(get_target_user),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PurgeResponse:
    """Hard purge (spec §8.2): password + typed email; past grace or ``force`` with a reason."""
    result = purge_service.purge_user(
        db,
        actor=actor,
        user=user,
        password=body.password,
        confirm_email=body.confirm_email,
        force=body.force,
        reason=body.reason,
        request=request,
    )
    db.commit()
    return result


@mutation_router.post("/maintenance/exercise-families", response_model=FamilyBackfillResponse)
async def backfill_exercise_families(
    request: Request,
    body: FamilyBackfillRequest,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FamilyBackfillResponse:
    """Exercise-family backfill (spec §7.3): dry run by default, apply is destructive tier."""
    result = admin_mutation_service.backfill_families(
        db,
        actor=actor,
        dry_run=body.dry_run,
        password=body.password,
        reason=body.reason,
        request=request,
    )
    db.commit()
    return result


@mutation_router.post("/maintenance/seed-achievements", response_model=SeedAchievementsResponse)
async def seed_achievements(
    request: Request,
    body: ReasonBody,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SeedAchievementsResponse:
    """Audited seed of the achievement definitions (spec §7.4)."""
    seeded = admin_mutation_service.seed_achievements(db, actor=actor, reason=body.reason, request=request)
    db.commit()
    return SeedAchievementsResponse(seeded=seeded)


@mutation_router.post("/maintenance/purge-eligible", response_model=PurgeSweepResponse)
async def purge_eligible(
    request: Request,
    body: PurgeSweepRequest,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PurgeSweepResponse:
    """The visible sweep (spec §8.3): list accounts past grace; ``dry_run=false`` purges them."""
    result = purge_service.purge_eligible(
        db,
        actor=actor,
        dry_run=body.dry_run,
        password=body.password,
        reason=body.reason,
        request=request,
    )
    db.commit()
    return result


@mutation_router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: Request,
    body: ProductUpsertRequest,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProductResponse:
    """Add a catalog SKU (spec §6.4). 409 if the id exists."""
    result = admin_mutation_service.upsert_product(db, actor=actor, body=body, request=request)
    db.commit()
    return result


@mutation_router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    request: Request,
    product_id: str,
    body: ProductUpsertRequest,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProductResponse:
    """Edit a SKU; the id is immutable and ``active=false`` is destructive tier (no DELETE)."""
    result = admin_mutation_service.upsert_product(
        db, actor=actor, body=body, product_id=product_id, request=request
    )
    db.commit()
    return result
