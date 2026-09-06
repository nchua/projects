"""
Hard purge and the startup sweep (control-plane spec §8.2, §8.3).

Only five child tables cascade from ``users.id``; the other twenty-one do
not, and a "add CASCADE everywhere" migration was rejected (§8.2). So
:data:`PURGE_ORDER` spells out every delete, child before parent, and the
metadata test in ``tests/test_admin_purge.py`` asserts that every table
with a foreign key to ``users.id`` appears in it. Two rows survive by
design: ``admin_audit_log`` (no FK — the trail outlives the account) and
``purchase_records`` (``user_id`` is set NULL; Apple holds the receipts).

``purge_user`` performs the checks and the deletes for one account and
audits ``user.purge`` in the same transaction; the route commits.
``purge_eligible`` lists (and, when not a dry run, purges) every account
past ``PURGE_GRACE_DAYS``, one transaction per user. ``run_startup_sweep``
is that call from the lifespan, behind ``PURGE_SWEEP_ENABLED`` and never on
SQLite.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import Table, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from starlette.requests import Request

from app.core.admin_auth import protect_account, verify_step_up
from app.core.config import settings
from app.core.database import Base
from app.core.dependencies import conflict, unprocessable
from app.core.utils import ensure_utc, to_naive_utc, utcnow
from app.models.user import User
from app.schemas.admin import PurgeEligibleRow, PurgeResponse, PurgeSweepResponse
from app.services.audit_service import audit

logger = logging.getLogger(__name__)

SWEEP_DELAY_SECONDS = 30
SWEEP_REASON = "startup sweep"
_BACKGROUND_TASKS: "set[asyncio.Task[str]]" = set()


def purge_eligible_cutoff(now: Optional[datetime] = None) -> datetime:
    """Accounts soft-deleted at or before this instant are past the grace period."""
    return (now or utcnow()) - timedelta(days=settings.PURGE_GRACE_DAYS)


def purge_eligible_at(deleted_at: datetime) -> datetime:
    """When a soft-deleted account becomes purge-eligible."""
    return deleted_at + timedelta(days=settings.PURGE_GRACE_DAYS)


@dataclass(frozen=True)
class PurgeStep:
    """One table in the purge: rows matched on ``columns`` (any of them)
    equal to the user id, or — with ``via`` — rows whose ``columns[0]`` is
    the id of a ``via`` row owned by the user. ``unlink`` sets ``user_id``
    NULL instead of deleting."""

    table: str
    columns: Tuple[str, ...] = ("user_id",)
    via: Optional[str] = None
    unlink: bool = False


# Child before parent for every FK that does not cascade (spec §8.2). Tables
# that only hang off these (campaign_arcs, hunt_templates, workout_exercises,
# sets) cascade at the database level and are not listed.
PURGE_ORDER: Tuple[PurgeStep, ...] = (
    PurgeStep("user_achievements"),
    PurgeStep("user_progress"),
    PurgeStep("prs"),                                   # before sets (prs.set_id)
    PurgeStep("pr_gates"),                              # before sets / planned_hunts
    PurgeStep("goal_progress_snapshots", ("goal_id",), via="goals"),
    PurgeStep("goals"),                                 # before campaigns (goals.campaign_id)
    PurgeStep("planned_hunts"),
    PurgeStep("campaigns"),                             # arcs / templates cascade
    PurgeStep("heart_rate_samples"),
    PurgeStep("workout_sessions"),                      # exercises / sets cascade
    PurgeStep("exercises"),                             # custom rows: seeds have user_id NULL
    PurgeStep("bodyweight_entries"),
    PurgeStep("daily_activity"),
    PurgeStep("daily_training_load"),
    PurgeStep("coach_outputs"),
    PurgeStep("user_directives"),
    PurgeStep("screenshot_usage"),
    PurgeStep("scan_balances"),
    PurgeStep("user_entitlements"),
    PurgeStep("password_reset_tokens"),
    PurgeStep("device_tokens"),
    PurgeStep("notification_preferences"),
    PurgeStep("whoop_connections"),
    PurgeStep("friend_requests", ("sender_id", "receiver_id")),
    PurgeStep("friendships", ("user_id", "friend_id")),
    PurgeStep("purchase_records", unlink=True),         # receipts outlive the account
    PurgeStep("user_profiles"),
    PurgeStep("users", ("id",)),
)


def _table(name: str) -> Table:
    return Base.metadata.tables[name]


def _where(step: PurgeStep, user_id: str) -> ColumnElement:
    table = _table(step.table)
    if step.via:
        parent = _table(step.via)
        owned = select(parent.c.id).where(parent.c.user_id == user_id)
        return table.c[step.columns[0]].in_(owned)
    return or_(*(table.c[column] == user_id for column in step.columns))


def _run_step(db: Session, step: PurgeStep, user_id: str) -> int:
    """Execute one step and return the number of rows deleted (or unlinked)."""
    table = _table(step.table)
    if step.unlink:
        statement = update(table).where(_where(step, user_id)).values(user_id=None)
    else:
        statement = delete(table).where(_where(step, user_id))
    return int(db.execute(statement).rowcount or 0)


def count_rows(db: Session, user_id: str) -> Dict[str, int]:
    """Rows each purge step would touch (what a purge will report as ``tables``)."""
    return {
        step.table: int(
            db.execute(
                select(func.count()).select_from(_table(step.table)).where(_where(step, user_id))
            ).scalar()
            or 0
        )
        for step in PURGE_ORDER
    }


def _purge_rows(
    db: Session,
    user: User,
    *,
    actor: Optional[User],
    reason: str,
    force: bool,
    request: Optional[Request] = None,
) -> Optional[PurgeResponse]:
    """The ordered deletes plus the ``user.purge`` audit row (no checks, no commit).

    None when the ``users`` row was already gone — another instance's sweep
    won the race (spec §8.3) — so no phantom zero-count audit row is written.
    An ``IntegrityError`` (a row in another account still pinning this
    user's data through a non-cascading FK) propagates for the caller to map.
    """
    user_id, deleted_at = user.id, user.deleted_at
    tables = {step.table: _run_step(db, step, user_id) for step in PURGE_ORDER}
    db.expunge(user)  # the row is gone; keep the session from re-loading it
    if tables["users"] == 0:
        return None
    row = audit(
        db,
        actor=actor,
        action="user.purge",
        target_type="user",
        target_id=user_id,
        before=tables,  # the rows that existed (each step's rowcount)
        after={"force": force},
        reason=reason,
        request=request,
    )
    return PurgeResponse(user_id=user_id, deleted_at=deleted_at, tables=tables, audit_id=row.id)


def purge_user(
    db: Session,
    *,
    actor: User,
    user: User,
    password: Optional[str],
    confirm_email: str,
    force: bool,
    reason: str,
    request: Optional[Request] = None,
) -> PurgeResponse:
    """Hard-delete one soft-deleted account (spec §8.2).

    Destructive tier plus a typed ``confirm_email``; 403 for admins and
    self; 409 unless soft-deleted and past ``PURGE_GRACE_DAYS`` — or
    ``force`` (the schema requires a reason of at least
    ``FORCE_REASON_MIN_LENGTH`` characters); 422 on a wrong ``confirm_email``.
    """
    verify_step_up(db, actor, password)
    protect_account(actor, user)
    if not user.is_deleted:
        raise conflict("Account is not soft-deleted")
    if confirm_email.strip().lower() != user.email.strip().lower():
        raise unprocessable("confirm_email does not match the account")
    deleted_at = ensure_utc(user.deleted_at)
    if not force and (deleted_at is None or deleted_at > purge_eligible_cutoff()):
        eligible = purge_eligible_at(deleted_at).isoformat() if deleted_at else "unknown"
        raise conflict(
            f"Inside the {settings.PURGE_GRACE_DAYS}-day grace period until {eligible}; send force=true"
        )
    try:
        result = _purge_rows(db, user, actor=actor, reason=reason, force=force, request=request)
    except IntegrityError as exc:
        db.rollback()
        raise conflict(f"Purge blocked: another account still references this user's data ({exc.orig})")
    if result is None:
        raise conflict("Account was already purged")
    return result


def eligible_filter(now: Optional[datetime] = None) -> Tuple[ColumnElement, ...]:
    """The one definition of "purge-eligible": soft-deleted, past grace, not an admin."""
    return (
        User.is_deleted == True,
        User.deleted_at <= to_naive_utc(purge_eligible_cutoff(now)),
        User.is_admin == False,
    )


def list_eligible(db: Session, now: datetime) -> Tuple[List[User], List[PurgeEligibleRow]]:
    """Eligible accounts, oldest first, with their response rows."""
    users = db.query(User).filter(*eligible_filter(now)).order_by(User.deleted_at, User.id).all()
    rows = [
        PurgeEligibleRow(
            user_id=u.id, deleted_at=u.deleted_at, days_deleted=(now - ensure_utc(u.deleted_at)).days
        )
        for u in users
    ]
    return users, rows


def sweep(
    db: Session, *, actor: Optional[User], reason: str, request: Optional[Request] = None
) -> PurgeSweepResponse:
    """Purge every eligible account, one committed transaction per user, then summarise.

    No authorisation here: the admin route does its step-up in
    :func:`purge_eligible`, the startup sweep runs as the system actor. A
    ``maintenance.purge_sweep`` row records the run (the caller commits it);
    an account pinned by a foreign row is skipped and listed as blocked.
    """
    users, eligible = list_eligible(db, utcnow())
    purged: List[PurgeResponse] = []
    blocked: List[str] = []
    for user in users:
        user_id = user.id
        try:
            result = _purge_rows(db, user, actor=actor, reason=reason, force=False, request=request)
            db.commit()
        except IntegrityError:
            db.rollback()
            blocked.append(user_id)
            logger.warning("purge sweep: user …%s blocked by a foreign reference", user_id[-4:])
            continue
        if result is not None:
            purged.append(result)
    audit(
        db,
        actor=actor,
        action="maintenance.purge_sweep",
        target_type="system",
        after={"eligible": len(eligible), "purged": [p.user_id for p in purged], "blocked": blocked},
        reason=reason,
        request=request,
    )
    return PurgeSweepResponse(dry_run=False, eligible=eligible, purged=purged)


def purge_eligible(
    db: Session,
    *,
    actor: User,
    dry_run: bool = True,
    password: Optional[str] = None,
    reason: str,
    request: Optional[Request] = None,
) -> PurgeSweepResponse:
    """``POST /admin/maintenance/purge-eligible``: list, or (destructive tier) :func:`sweep`."""
    if dry_run:
        _, eligible = list_eligible(db, utcnow())
        return PurgeSweepResponse(dry_run=True, eligible=eligible)
    verify_step_up(db, actor, password)
    return sweep(db, actor=actor, reason=reason, request=request)


# ── startup sweep (spec §8.3) ───────────────────────────────────────────────

def run_startup_sweep() -> str:
    """The boot-time sweep body. Returns ``disabled`` / ``sqlite`` / ``ok`` / ``error``.

    Gated by ``PURGE_SWEEP_ENABLED`` (default false) and skipped on SQLite
    so tests and a local run are inert. Never raises.
    """
    if not settings.PURGE_SWEEP_ENABLED:
        return "disabled"
    from app.core import database  # resolved at call time so tests can patch SessionLocal

    bind = database.SessionLocal.kw.get("bind")
    if bind is not None and bind.dialect.name == "sqlite":
        return "sqlite"
    try:
        db = database.SessionLocal()
        try:
            result = sweep(db, actor=None, reason=SWEEP_REASON)
            db.commit()
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - the sweep must never take the app down
        logger.exception("purge sweep failed")
        return "error"
    logger.info("purge sweep: %d eligible, %d purged", len(result.eligible), len(result.purged))
    return "ok"


def schedule_startup_sweep(delay: float = SWEEP_DELAY_SECONDS) -> Optional["asyncio.Task[str]"]:
    """Fire-and-forget :func:`run_startup_sweep` ``delay`` seconds after boot.

    Returns the task, or None when the flag is off or no event loop is
    running (a synchronous caller outside the lifespan).
    """
    if not settings.PURGE_SWEEP_ENABLED:
        return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("purge sweep: no running event loop — not scheduled")
        return None

    async def _later() -> str:
        await asyncio.sleep(delay)
        return await asyncio.to_thread(run_startup_sweep)

    task = loop.create_task(_later())
    _BACKGROUND_TASKS.add(task)  # asyncio only holds weak refs to tasks
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task
