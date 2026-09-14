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
SQLite. Both numbers come through ``settings_service`` (console row → env →
code, console v2 §6.5), so the owner can move the grace window or arm the
sweep without a redeploy; the sweep reads its gate inside the session it
opens, so a console flip counts on the next boot.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Table, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from starlette.requests import Request

from app.core.admin_auth import protect_account, verify_step_up
from app.core.database import Base
from app.core.dependencies import conflict, unprocessable
from app.core.utils import ensure_utc, to_naive_utc, utcnow
from app.models.user import User
from app.schemas.admin import (
    BulkPurgePreviewRow,
    BulkPurgeRequest,
    BulkPurgeResponse,
    PurgeEligibleRow,
    PurgeResponse,
    PurgeSweepResponse,
)
from app.services import settings_service
from app.services.audit_service import audit
from app.services.bulk import Skip, per_user

logger = logging.getLogger(__name__)

SWEEP_DELAY_SECONDS = 30
SWEEP_REASON = "startup sweep"
_BACKGROUND_TASKS: "set[asyncio.Task[str]]" = set()


def grace_days(db: Session) -> int:
    """``PURGE_GRACE_DAYS`` in force (console row → env → code)."""
    return int(settings_service.get(db, "PURGE_GRACE_DAYS"))


def sweep_enabled(db: Session) -> bool:
    """``PURGE_SWEEP_ENABLED`` in force (console row → env → code)."""
    return bool(settings_service.get(db, "PURGE_SWEEP_ENABLED"))


def purge_eligible_cutoff(db: Session, now: Optional[datetime] = None) -> datetime:
    """Accounts soft-deleted at or before this instant are past the grace period."""
    return (now or utcnow()) - timedelta(days=grace_days(db))


def purge_eligible_at(db: Session, deleted_at: datetime) -> datetime:
    """When a soft-deleted account becomes purge-eligible."""
    return deleted_at + timedelta(days=grace_days(db))


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
    if not force and (deleted_at is None or deleted_at > purge_eligible_cutoff(db)):
        eligible = purge_eligible_at(db, deleted_at).isoformat() if deleted_at else "unknown"
        raise conflict(
            f"Inside the {grace_days(db)}-day grace period until {eligible}; send force=true"
        )
    try:
        result = _purge_rows(db, user, actor=actor, reason=reason, force=force, request=request)
    except IntegrityError as exc:
        db.rollback()
        raise conflict(f"Purge blocked: another account still references this user's data ({exc.orig})")
    if result is None:
        raise conflict("Account was already purged")
    return result


def eligible_filter_at(cutoff: datetime) -> Tuple[ColumnElement, ...]:
    """The one SQL definition of "purge-eligible": soft-deleted at or before ``cutoff`` (naive UTC), not an admin."""
    return (User.is_deleted == True, User.deleted_at <= cutoff, User.is_admin == False)


def eligible_filter(db: Session, now: Optional[datetime] = None) -> Tuple[ColumnElement, ...]:
    """:func:`eligible_filter_at` with the cutoff resolved from ``PURGE_GRACE_DAYS``."""
    return eligible_filter_at(to_naive_utc(purge_eligible_cutoff(db, now)))


def is_purge_eligible_at(user: User, cutoff: datetime) -> bool:
    """Python twin of :func:`eligible_filter` for one loaded row, given the grace ``cutoff``."""
    deleted_at = ensure_utc(user.deleted_at)
    return bool(user.is_deleted) and not bool(user.is_admin) and deleted_at is not None and deleted_at <= cutoff


def is_purge_eligible(db: Session, user: User, now: Optional[datetime] = None) -> bool:
    """:func:`is_purge_eligible_at` with the cutoff resolved from ``PURGE_GRACE_DAYS``."""
    return is_purge_eligible_at(user, purge_eligible_cutoff(db, now))


def list_eligible(db: Session, now: datetime) -> Tuple[List[User], List[PurgeEligibleRow]]:
    """Eligible accounts, oldest first, with their response rows."""
    users = db.query(User).filter(*eligible_filter(db, now)).order_by(User.deleted_at, User.id).all()
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


# ── bulk purge (console v2 §5.4, §6.4) ──────────────────────────────────────

def bulk_purge(
    db: Session, *, actor: User, body: BulkPurgeRequest, request: Optional[Request] = None
) -> BulkPurgeResponse:
    """``POST /admin/users/purge``: every id must be purge-eligible (422 naming the first
    that is not); a dry run lists each account's table counts; apply needs the password and
    ``confirm_count == len(user_ids)``, then purges one committed transaction per user."""
    cutoff = purge_eligible_cutoff(db)
    ids = list(dict.fromkeys(body.user_ids))
    users = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}
    for user_id in ids:
        user = users.get(user_id)
        if user is None:
            raise unprocessable(f"{user_id} not found")
        if not is_purge_eligible_at(user, cutoff):
            raise unprocessable(f"{user_id} is not purge-eligible")

    if body.dry_run:
        preview = [BulkPurgePreviewRow(user_id=uid, tables=count_rows(db, uid)) for uid in ids]
        return BulkPurgeResponse(dry_run=True, preview=preview)

    verify_step_up(db, actor, body.password)
    if body.confirm_count != len(ids):
        raise unprocessable(f"confirm_count must equal the number of accounts ({len(ids)})")

    def step(user: User) -> PurgeResponse:
        try:
            result = _purge_rows(db, user, actor=actor, reason=body.reason, force=False, request=request)
        except IntegrityError as exc:
            raise conflict(f"another account still references this user's data ({exc.orig})")
        if result is None:
            raise Skip("already purged")
        return result

    applied, skipped, failed = per_user(db, ids, step)
    return BulkPurgeResponse(dry_run=False, applied=applied, skipped=skipped, failed=failed)


# ── startup sweep (spec §8.3) ───────────────────────────────────────────────

def _is_sqlite(bind: Any) -> bool:
    return bind is not None and bind.dialect.name == "sqlite"


def startup_sweep(db: Session) -> str:
    """The boot-time sweep body on a given session: ``disabled`` / ``sqlite`` / ``ok``.

    Gated by ``PURGE_SWEEP_ENABLED`` — read through the resolver, so a
    console flip arms the next boot without a redeploy — and skipped on
    SQLite so a local run is inert. The session is the seam tests use.
    """
    if not sweep_enabled(db):
        return "disabled"
    if _is_sqlite(db.get_bind()):
        return "sqlite"
    result = sweep(db, actor=None, reason=SWEEP_REASON)
    db.commit()
    logger.info("purge sweep: %d eligible, %d purged", len(result.eligible), len(result.purged))
    return "ok"


def run_startup_sweep() -> str:
    """:func:`startup_sweep` on a fresh ``SessionLocal()``; never raises (``error`` instead)."""
    from app.core import database  # resolved at call time so tests can patch SessionLocal

    try:
        db = database.SessionLocal()
        try:
            return startup_sweep(db)
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - the sweep must never take the app down
        logger.exception("purge sweep failed")
        return "error"


def schedule_startup_sweep(delay: float = SWEEP_DELAY_SECONDS) -> Optional["asyncio.Task[str]"]:
    """Fire-and-forget :func:`run_startup_sweep` ``delay`` seconds after boot.

    The flag is not checked here — the task reads it when it fires, so the
    console can arm the sweep after boot-time env parsing. Returns the task,
    or None on SQLite (the sweep never runs there; keeps tests and local runs
    free of a background task) or when no event loop is running.
    """
    from app.core import database  # resolved at call time so tests can patch the engine

    if _is_sqlite(database.engine):
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
