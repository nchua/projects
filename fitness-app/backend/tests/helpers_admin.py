"""Shared helpers for the control-plane (admin) tests.

``MUTATIONS`` is the registry every parametrized admin test walks: one
entry per mutation route (spec §13), each knowing how to set up its target
and build a valid call. ``test_admin_step_up`` drives the destructive ones
with a wrong password, ``test_admin_audit`` drives all of them and expects
exactly one audit row, and the route-enumeration gate uses them for the
200/201 leg.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from types import ModuleType
from typing import Any, Callable, Dict, Iterator, List, Tuple

from starlette.requests import Request

from app.core.utils import utcnow
from app.models.entitlement import Product
from app.models.scan_balance import ScanBalance
from app.services import entitlement_service as es
from tests.helpers_migrations import BACKEND, load_module
from tests.helpers_w1 import MONDAY, import_plan

# Key shapes that must never appear in an admin response or audit payload.
SECRET_EXACT = {"password", "password_hash", "code", "token", "secret", "secret_key"}
SECRET_SUFFIX = ("_token", "_encrypted", "_secret", "_hash")


def make_request(path: str = "/admin/me", method: str = "GET") -> Request:
    """A bare Starlette request for calling dependencies directly."""
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "query_string": b"",
        }
    )


def load_script(name: str) -> ModuleType:
    return load_module(BACKEND / "scripts" / f"{name}.py", f"owner_script_{name}")


def grant_admin(db, user_id: str, key: str, value: Any):
    """Admin-sourced grant with the common arguments filled in (no commit)."""
    return es.grant(db, user_id=user_id, key=key, value=value, source="admin_grant")


def walk_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from walk_keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk_keys(v)


def assert_no_secret_keys(payload: Any) -> None:
    leaked = {
        k for k in walk_keys(payload)
        if k.lower() in SECRET_EXACT or k.lower().endswith(SECRET_SUFFIX)
    }
    assert not leaked, f"secret-shaped keys in admin payload: {sorted(leaked)}"


def soft_delete(db, user, days_ago: int = 0) -> None:
    user.is_deleted = True
    user.deleted_at = utcnow() - timedelta(days=days_ago)
    db.commit()


def balance_of(db, user_id: str) -> ScanBalance:
    """The user's balance row, re-read from the database."""
    db.expire_all()
    return db.query(ScanBalance).filter(ScanBalance.user_id == user_id).one()


def step_up_body(password: str = "TestPass123!", reason: str = "test reason", **extra: Any) -> Dict[str, Any]:
    """A destructive-tier body (spec §4.5); keyword extras merge in (``confirm_email=…``, ``force=True``)."""
    return {"password": password, "reason": reason, **extra}


def product_body(product_id: str, **overrides: Any) -> Dict[str, Any]:
    """A full ``ProductUpsertRequest`` body for ``product_id``."""
    body = {
        "id": product_id, "kind": "consumable", "credits": 5, "entitlement_key": None,
        "display_name": "Test pack", "active": True, "sort_order": 9, "reason": "test product",
    }
    body.update(overrides)
    return body


# ── the mutation registry ───────────────────────────────────────────────────


@dataclass
class MutationContext:
    """What a case needs to build its call: the session, the actor, a fresh target."""

    db: Any
    actor: Any
    target: Any
    password: str
    tag: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class Call:
    method: str
    path: str
    json: Dict[str, Any]
    headers: Dict[str, str] = field(default_factory=dict)
    expect: int = 200


@dataclass(frozen=True)
class MutationCase:
    name: str
    action: str                    # the audit action the call writes
    route: Tuple[str, str]         # (method, path template) as registered on the app
    destructive: bool              # needs ``password`` (spec §4.5)
    build: Callable[[MutationContext], Call]

    def __repr__(self) -> str:  # pytest ids
        return self.name


def _step_up(ctx: MutationContext, **extra: Any) -> Dict[str, Any]:
    return step_up_body(password=ctx.password, **extra)


def _credits(delta: int):
    def build(ctx: MutationContext) -> Call:
        body: Dict[str, Any] = {"delta": delta, "reason": "test credits"}
        if abs(delta) > 50:
            body["password"] = ctx.password
        return Call(
            "POST", f"/admin/users/{ctx.target.id}/credits", body,
            headers={"Idempotency-Key": f"key-{ctx.tag}"},
        )
    return build


def _grant(ctx: MutationContext) -> Call:
    return Call(
        "POST", f"/admin/users/{ctx.target.id}/entitlements",
        {"key": es.KEY_DAILY_LIMIT, "value": 5, "reason": "test grant"}, expect=201,
    )


def _revoke(ctx: MutationContext) -> Call:
    row = grant_admin(ctx.db, ctx.target.id, es.KEY_DAILY_LIMIT, 5)
    ctx.db.commit()
    return Call("POST", f"/admin/users/{ctx.target.id}/entitlements/{row.id}/revoke", _step_up(ctx))


def _campaign_import(replace: bool):
    def build(ctx: MutationContext) -> Call:
        if replace:
            import_plan(ctx.db, ctx.target.id)
        body: Dict[str, Any] = {
            "name": "Test plan", "template": "owner_hybrid", "reason": "test import",
            "replace": replace, "client_date": MONDAY.isoformat(),
        }
        if replace:
            body["password"] = ctx.password
        return Call("POST", f"/admin/users/{ctx.target.id}/campaign/import", body, expect=201)
    return build


def _families_apply(ctx: MutationContext) -> Call:
    return Call("POST", "/admin/maintenance/exercise-families", _step_up(ctx, dry_run=False))


def _seed(ctx: MutationContext) -> Call:
    return Call("POST", "/admin/maintenance/seed-achievements", {"reason": "test seed"})


def _sweep_apply(ctx: MutationContext) -> Call:
    return Call("POST", "/admin/maintenance/purge-eligible", _step_up(ctx, dry_run=False))


def _soft_delete(ctx: MutationContext) -> Call:
    return Call("POST", f"/admin/users/{ctx.target.id}/delete", _step_up(ctx))


def _restore(ctx: MutationContext) -> Call:
    soft_delete(ctx.db, ctx.target)
    return Call("POST", f"/admin/users/{ctx.target.id}/restore", _step_up(ctx))


def _purge_force(ctx: MutationContext) -> Call:
    soft_delete(ctx.db, ctx.target)
    return Call(
        "POST", f"/admin/users/{ctx.target.id}/purge",
        _step_up(ctx, reason="forced purge for a test", confirm_email=ctx.target.email, force=True),
    )


def _purge_past_grace(ctx: MutationContext) -> Call:
    soft_delete(ctx.db, ctx.target, days_ago=40)
    return Call(
        "POST", f"/admin/users/{ctx.target.id}/purge",
        _step_up(ctx, confirm_email=ctx.target.email),
    )


def _product_create(ctx: MutationContext) -> Call:
    return Call("POST", "/admin/products", product_body(f"com.test.{ctx.tag}"), expect=201)


def _product_deactivate(ctx: MutationContext) -> Call:
    product_id = f"com.test.{ctx.tag}"
    ctx.db.add(Product(**{k: v for k, v in product_body(product_id).items() if k != "reason"}))
    ctx.db.commit()
    return Call(
        "PATCH", f"/admin/products/{product_id}",
        product_body(product_id, active=False, password=ctx.password),
    )


MUTATIONS: List[MutationCase] = [
    MutationCase("credits_small", "credits.adjust", ("POST", "/admin/users/{user_id}/credits"), False, _credits(5)),
    MutationCase("credits_large", "credits.adjust", ("POST", "/admin/users/{user_id}/credits"), True, _credits(60)),
    MutationCase("grant", "entitlement.grant", ("POST", "/admin/users/{user_id}/entitlements"), False, _grant),
    MutationCase("revoke", "entitlement.revoke", ("POST", "/admin/users/{user_id}/entitlements/{entitlement_id}/revoke"), True, _revoke),
    MutationCase("campaign_import", "campaign.import", ("POST", "/admin/users/{user_id}/campaign/import"), False, _campaign_import(False)),
    MutationCase("campaign_replace", "campaign.import", ("POST", "/admin/users/{user_id}/campaign/import"), True, _campaign_import(True)),
    MutationCase("families_apply", "maintenance.family_backfill", ("POST", "/admin/maintenance/exercise-families"), True, _families_apply),
    MutationCase("seed_achievements", "maintenance.seed_achievements", ("POST", "/admin/maintenance/seed-achievements"), False, _seed),
    MutationCase("purge_sweep_apply", "maintenance.purge_sweep", ("POST", "/admin/maintenance/purge-eligible"), True, _sweep_apply),
    MutationCase("soft_delete", "user.soft_delete", ("POST", "/admin/users/{user_id}/delete"), True, _soft_delete),
    MutationCase("restore", "user.restore", ("POST", "/admin/users/{user_id}/restore"), True, _restore),
    MutationCase("purge_force", "user.purge", ("POST", "/admin/users/{user_id}/purge"), True, _purge_force),
    MutationCase("purge_past_grace", "user.purge", ("POST", "/admin/users/{user_id}/purge"), True, _purge_past_grace),
    MutationCase("product_create", "product.upsert", ("POST", "/admin/products"), False, _product_create),
    MutationCase("product_deactivate", "product.upsert", ("PATCH", "/admin/products/{product_id}"), True, _product_deactivate),
]

DESTRUCTIVE = [case for case in MUTATIONS if case.destructive]
CASES = {case.name: case for case in MUTATIONS}
CASE_BY_ROUTE = {case.route: case for case in reversed(MUTATIONS)}  # first listed case wins


def drive(client, headers: Dict[str, str], case: MutationCase, ctx: MutationContext, **extra_headers):
    """Build and send one case's call with the admin ``headers``."""
    call = case.build(ctx)
    return client.request(
        call.method, call.path, json=call.json, headers={**headers, **call.headers, **extra_headers}
    ), call
