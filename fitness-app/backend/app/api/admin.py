"""
Owner console API — the ``/admin/*`` read surfaces (control-plane spec §9, §13).

Two routers, both mounted under ``/admin`` and hidden from OpenAPI:

* ``session_router`` — ``POST /admin/session`` only. It runs *before*
  ``require_admin`` (there is no token yet), so it is rate-limited with the
  login policy and stamps ``request.state.audit_ip`` itself so the
  ``session.create`` audit row carries the caller's IP.
* ``router`` — everything else, with ``require_admin`` attached at the
  router level so no handler can forget it.

Read handlers take ``Depends(get_read_only_db)``: the same request session,
marked read-only on Postgres so an accidental write fails loudly (spec §9.3).
W2's mutation handlers take plain ``get_db``.

``Cache-Control: no-store`` (and ``X-Frame-Options: DENY``) on every
``/admin/*`` response is added by ``AdminResponseHeadersMiddleware`` in
``main.py`` so error responses carry it too.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.admin_auth import require_admin
from app.core.database import get_db, mark_read_only
from app.core.rate_limit import LOGIN_RATE_LIMIT, client_ip, limiter
from app.models.user import User
from app.schemas.admin import (
    AdminMeResponse,
    AdminSessionRequest,
    AdminSessionResponse,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AuditListResponse,
    FleetUsageResponse,
    ProductResponse,
    SortOrder,
    UserSort,
    UserUsageResponse,
)
from app.services import admin_service, admin_usage_service

session_router = APIRouter()
router = APIRouter(dependencies=[Depends(require_admin)])


def get_read_only_db(db: Session = Depends(get_db)) -> Session:
    """The request session, marked read-only where the dialect supports it."""
    mark_read_only(db)
    return db


def get_target_user(user_id: str, db: Session = Depends(get_db)) -> User:
    """The ``{user_id}`` path target (deleted accounts included), or 404."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# ── session (no admin token yet) ────────────────────────────────────────────

@session_router.post("/session", response_model=AdminSessionResponse)
@limiter.limit(LOGIN_RATE_LIMIT)
async def create_session(
    request: Request, body: AdminSessionRequest, db: Session = Depends(get_db)
):
    """Mint a 15-minute admin token (spec §4.2). 401 / 403 / 423 per the service."""
    request.state.audit_ip = client_ip(request)
    token, expires_at = admin_service.mint_admin_session(
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
    items, total = admin_service.list_users(
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
    return admin_service.get_user_detail(db, user)


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
    items, total = admin_service.list_audit(
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
    return admin_service.list_products(db)
