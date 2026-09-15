"""
Owner console read surfaces (control-plane spec §9, §13, §16):
``POST /admin/session``, ``GET /admin/me``, the route-enumeration gate,
``GET /admin/users`` (filters / sort / paging), ``GET /admin/users/{id}``
(every block on a fresh user, never a secret), ``GET /admin/products``.
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Set, Tuple

import pytest

from app.core.database import Base
from app.core.security import create_access_token, create_admin_token, user_token_claims
from app.models.admin import AdminAuditLog
from app.models.exercise import Exercise
from app.models.notification import DeviceToken
from app.models.progress import UserProgress
from app.models.scan_balance import PurchaseRecord, ScanBalance
from app.models.screenshot_usage import ScreenshotUsage
from app.models.training_load import DailyTrainingLoad
from app.models.whoop import WhoopConnection
from app.models.workout import WorkoutSession
from app.services import admin_read_service, settings_service
from app.services import entitlement_service as es
from app.services.campaign_service import materialize_range
from app.services.training_load_service import get_load_state
from main import app
from tests.helpers_admin import (
    CASE_BY_ROUTE,
    MutationContext,
    assert_no_secret_keys,
    drive,
    grant_admin,
)
from tests.helpers_w1 import MONDAY, add_lift, import_plan

TODAY = date.today()
SESSION_ROUTE = ("POST", "/admin/session")

def _admin_routes() -> List[Tuple[str, str]]:
    """Every (method, path) under /admin except the public session mint."""
    out: List[Tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/admin"):
            continue
        for method in sorted(getattr(route, "methods", None) or []):
            if (method, path) != SESSION_ROUTE:
                out.append((method, path))
    return out


def _fill(path: str) -> str:
    return path.replace("{user_id}", "no-such-user").replace("{", "").replace("}", "")


def _row_counts(db) -> dict:
    """Row count of every mapped table — the write-free proof for read routes."""
    from sqlalchemy import func, select

    return {t.name: db.execute(select(func.count()).select_from(t)).scalar() for t in Base.metadata.sorted_tables}


def _session(db, user_id: str, day: date, *, local: bool = True) -> WorkoutSession:
    """A bare session on ``day``: stamped at 10:00, or a legacy 03:30Z instant with no local_date."""
    instant = datetime.combine(day, time(10, 0) if local else time(3, 30))
    return add_lift(db, user_id, day, [], instant=instant, stamp_local=local, duration_minutes=45)


class TestSession:
    def test_mint_and_use_token(self, client, db, admin_user):
        user, pwd = admin_user(email="sess-ok@example.com")
        response = client.post(
            "/admin/session",
            json={"email": user.email, "password": pwd},
            headers={"X-Request-ID": "req-sess-1", "X-Forwarded-For": "203.0.113.9"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {"admin_token", "expires_at"}
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-frame-options"] == "DENY"

        me = client.get("/admin/me", headers={"Authorization": f"Bearer {body['admin_token']}"})
        assert me.status_code == 200
        assert me.json()["user_id"] == user.id

        row = (
            db.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "session.create", AdminAuditLog.actor_user_id == user.id)
            .one()
        )
        # The route runs before require_admin, so it must stamp the ip itself
        # (the TestClient sends no peer address; the proxy header is the signal).
        assert row.ip == "203.0.113.9"
        assert row.request_id == "req-sess-1"

    def test_bad_password_401_non_admin_403_malformed_422(self, client, admin_user, create_test_user):
        admin, _ = admin_user(email="sess-bad@example.com")
        plain, pwd = create_test_user(email="sess-plain@example.com")
        assert client.post(
            "/admin/session", json={"email": admin.email, "password": "nope"}
        ).status_code == 401
        assert client.post(
            "/admin/session", json={"email": plain.email, "password": pwd}
        ).status_code == 403
        assert client.post("/admin/session", json={"email": "not-an-email"}).status_code == 422

    def test_login_rate_limit_applies(self, client, admin_user):
        user, _ = admin_user(email="sess-rl@example.com")
        for _ in range(5):
            assert client.post(
                "/admin/session", json={"email": user.email, "password": "wrong"}
            ).status_code == 401
        blocked = client.post("/admin/session", json={"email": user.email, "password": "wrong"})
        assert blocked.status_code == 429
        assert blocked.headers["cache-control"] == "no-store"


class TestMe:
    def test_reports_token_expiry(self, client, admin_headers):
        headers, user = admin_headers(email="me@example.com")
        response = client.get("/admin/me", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == user.id
        expires = datetime.fromisoformat(body["token_expires_at"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        assert now < expires <= now + timedelta(minutes=16)
        assert response.headers["cache-control"] == "no-store"


class TestRouteEnumeration:
    def test_every_admin_route_is_hidden_from_openapi(self):
        hidden = [r for r in app.routes if getattr(r, "path", "").startswith("/admin")]
        assert hidden, "no /admin routes registered"
        # a Mount (the static console) has no include_in_schema and can never reach the schema
        assert all(getattr(r, "include_in_schema", False) is False for r in hidden)
        assert not any(p.startswith("/admin") for p in app.openapi()["paths"])

    def test_no_mutating_route_under_audit(self):
        for method, path in _admin_routes():
            if path.startswith("/admin/audit"):
                assert method == "GET", (method, path)

    def test_no_delete_route_anywhere_under_admin(self):
        """Products deactivate, accounts soft-delete, purge is a POST (spec §6.4, §8)."""
        assert not [(m, p) for m, p in _admin_routes() if m == "DELETE"]

    def test_every_mutation_route_is_in_the_registry(self):
        mutating = {(m, p) for m, p in _admin_routes() if m != "GET"}
        assert mutating == set(CASE_BY_ROUTE)

    @pytest.mark.parametrize("method,path", _admin_routes())
    def test_gate(self, client, db, create_test_user, admin_headers, method, path):
        url = _fill(path)
        plain, _ = create_test_user(email=f"gate-{uuid.uuid4().hex[:8]}@example.com")
        access = create_access_token(data=user_token_claims(plain))
        admin_shaped, _ = create_admin_token(plain)  # admin token for a NON-admin user

        no_token = client.request(method, url)
        assert no_token.status_code == 401, (method, path, no_token.text)
        assert no_token.headers["cache-control"] == "no-store"

        with_access = client.request(method, url, headers={"Authorization": f"Bearer {access}"})
        assert with_access.status_code == 401, (method, path, with_access.text)

        non_admin = client.request(
            method, url, headers={"Authorization": f"Bearer {admin_shaped}"}
        )
        assert non_admin.status_code == 403, (method, path, non_admin.text)

        headers, actor = admin_headers(email=f"gate-admin-{uuid.uuid4().hex[:8]}@example.com")
        if method == "GET":  # the 200 leg: a real admin against a real user id
            ok = client.get(path.replace("{user_id}", plain.id), headers=headers)
            expected = 200
        else:  # the 200/201 leg: the registry knows how to drive every mutation route
            ctx = MutationContext(db=db, actor=actor, target=plain, password="TestPass123!")
            ok, call = drive(client, headers, CASE_BY_ROUTE[(method, path)], ctx)
            expected = call.expect
        assert ok.status_code == expected, (method, path, ok.text)
        assert ok.headers["cache-control"] == "no-store"
        assert_no_secret_keys(ok.json())


@pytest.fixture
def hunters(db, create_test_user):
    """Four accounts covering the list filters. Returns a dict by role."""
    tag = uuid.uuid4().hex[:6]
    active, _ = create_test_user(email=f"active-{tag}@example.com")
    active.username = f"act{tag}"
    stale, _ = create_test_user(email=f"stale-{tag}@example.com")
    gone, _ = create_test_user(email=f"gone-{tag}@example.com")
    gone.is_deleted = True
    gone.deleted_at = datetime.now(timezone.utc) - timedelta(days=3)
    rich, _ = create_test_user(email=f"rich-{tag}@example.com")
    db.commit()

    _session(db, active.id, TODAY - timedelta(days=1))                    # stamped local day
    _session(db, active.id, TODAY - timedelta(days=9), local=False)       # legacy UTC instant
    _session(db, stale.id, TODAY - timedelta(days=60))
    deleted = _session(db, stale.id, TODAY)                               # soft-deleted → ignored
    deleted.deleted_at = datetime.now(timezone.utc)
    db.add(ScanBalance(user_id=rich.id, scan_credits=42, has_unlimited=False))
    db.add(ScanBalance(user_id=active.id, scan_credits=1, has_unlimited=False))
    db.commit()
    grant_admin(db, rich.id, es.KEY_UNLIMITED, True)
    db.commit()
    return {"tag": tag, "active": active, "stale": stale, "gone": gone, "rich": rich}


class TestListUsers:
    def _ids(self, client, headers, **params) -> Tuple[List[str], int]:
        response = client.get("/admin/users", headers=headers, params=params)
        assert response.status_code == 200, response.text
        body = response.json()
        assert_no_secret_keys(body)
        return [row["id"] for row in body["items"]], body["total"]

    def test_search_and_row_shape(self, client, admin_headers, hunters):
        headers, _ = admin_headers(email="owner-search@example.com")
        response = client.get("/admin/users", headers=headers, params={"q": f"active-{hunters['tag']}"})
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        row = body["items"][0]
        assert row["id"] == hunters["active"].id
        assert row["email"] == hunters["active"].email
        assert row["username"] == hunters["active"].username
        assert row["session_count"] == 2
        assert row["last_workout_date"] == (TODAY - timedelta(days=1)).isoformat()
        assert row["scan_credits"] == 1 and row["has_unlimited"] is False
        assert row["is_deleted"] is False and row["is_admin"] is False
        assert set(row) == {
            "id", "email", "username", "created_at", "is_deleted", "deleted_at", "is_admin",
            "level", "rank", "last_workout_date", "session_count", "scan_credits", "has_unlimited",
            # console v2 §6.2
            "plan", "plan_source", "plan_expires_at", "purchased_credits", "free_monthly",
            "status", "last_active", "last_active_kind", "scans_4wk", "override_keys",
        }
        assert row["plan"] == "free" and row["status"] == "active"
        assert row["last_active"] == row["last_workout_date"] and row["last_active_kind"] == "workout"
        # username search hits too
        ids, _ = self._ids(client, headers, q=f"act{hunters['tag']}")
        assert ids == [hunters["active"].id]

    def test_legacy_instant_falls_back_to_utc_day(self, client, db, admin_headers, hunters):
        headers, _ = admin_headers(email="owner-legacy@example.com")
        # Soft-delete the stamped row: only the legacy (local_date NULL, 03:30Z) row remains,
        # so the list must fall back to that instant's UTC calendar day.
        stamped = (
            db.query(WorkoutSession)
            .filter(WorkoutSession.user_id == hunters["active"].id,
                    WorkoutSession.local_date.isnot(None))
            .one()
        )
        stamped.deleted_at = datetime.now(timezone.utc)
        db.commit()
        row = client.get(
            "/admin/users", headers=headers, params={"q": f"active-{hunters['tag']}"}
        ).json()["items"][0]
        assert row["session_count"] == 1
        assert row["last_workout_date"] == (TODAY - timedelta(days=9)).isoformat()

    def test_filters(self, client, admin_headers, hunters, db):
        tag = hunters["tag"]
        headers, _ = admin_headers(email="owner-filters@example.com")
        ids, total = self._ids(client, headers, q=tag, deleted="true")
        assert ids == [hunters["gone"].id] and total == 1
        ids, _ = self._ids(client, headers, q=tag, deleted="false")
        assert hunters["gone"].id not in ids and len(ids) == 3
        ids, _ = self._ids(client, headers, q=tag, unlimited="true")
        assert ids == [hunters["rich"].id]
        ids, _ = self._ids(client, headers, q=tag, unlimited="false")
        assert hunters["rich"].id not in ids and hunters["active"].id in ids
        ids, _ = self._ids(client, headers, q=tag, active_days=7)
        assert ids == [hunters["active"].id]
        ids, _ = self._ids(client, headers, q=tag, active_days=90)
        assert set(ids) == {hunters["active"].id, hunters["stale"].id}

    def test_sort_and_paging(self, client, admin_headers, hunters):
        tag = hunters["tag"]
        headers, _ = admin_headers(email="owner-sort@example.com")
        # v2 defaults to status=active,inactive; ask for every status to keep the deleted row.
        every = {"q": tag, "status": "active,inactive,deleted,purge_eligible"}
        emails_asc, _ = self._ids(client, headers, sort="email", order="asc", **every)
        emails_desc, _ = self._ids(client, headers, sort="email", order="desc", **every)
        assert emails_asc == list(reversed(emails_desc))
        assert emails_asc[0] == hunters["active"].id  # "active-…" sorts first

        credits, _ = self._ids(client, headers, sort="credits", order="desc", **every)
        assert credits[:2] == [hunters["rich"].id, hunters["active"].id]  # 42, 1, then NULLs

        last_active, _ = self._ids(client, headers, sort="last_active", order="desc", **every)
        assert last_active[:2] == [hunters["active"].id, hunters["stale"].id]

        page1, total = self._ids(client, headers, sort="email", order="asc", limit=2, **every)
        page2, _ = self._ids(client, headers, sort="email", order="asc", limit=2, offset=2, **every)
        assert total == 4 and len(page1) == 2 and len(page2) == 2
        assert page1 + page2 == emails_asc

    def test_search_escapes_like_wildcards(self, client, db, admin_headers, create_test_user):
        headers, _ = admin_headers(email="owner-like@example.com")
        tag = uuid.uuid4().hex[:6]
        literal, _ = create_test_user(email=f"pct-{tag}@example.com")
        literal.username = f"a_b{tag}"
        create_test_user(email=f"plain-{tag}@example.com")
        db.commit()
        # "_" is a LIKE single-char wildcard; escaped, it only matches the literal underscore.
        ids, total = self._ids(client, headers, q=f"a_b{tag}")
        assert ids == [literal.id] and total == 1
        ids, _ = self._ids(client, headers, q=f"%{tag}")
        assert ids == []

    def test_invalid_params_422(self, client, admin_headers):
        headers, _ = admin_headers(email="owner-422@example.com")
        assert client.get("/admin/users", headers=headers, params={"sort": "xp"}).status_code == 422
        assert client.get("/admin/users", headers=headers, params={"limit": 0}).status_code == 422
        assert client.get("/admin/users", headers=headers, params={"active_days": 0}).status_code == 422


@pytest.fixture
def plan_cohort(db, create_test_user):
    """One hunter per plan (plus the unlimited + override and expired-unlimited edges) and per status."""
    tag = uuid.uuid4().hex[:6]
    free_default = int(settings_service.get(db, "FREE_MONTHLY_SCANS"))

    def make(name):
        user, _ = create_test_user(email=f"{name}-{tag}@example.com")
        return user

    free, credits, override, unlimited, both, expired = (
        make(n) for n in ("pfree", "pcredits", "poverride", "punlimited", "pboth", "pexpired")
    )
    db.add(ScanBalance(user_id=credits.id, scan_credits=free_default + 30, has_unlimited=False))
    db.add(ScanBalance(user_id=override.id, scan_credits=free_default + 30, has_unlimited=False))
    db.add(ScanBalance(user_id=expired.id, scan_credits=free_default, has_unlimited=False))
    db.commit()
    grant_admin(db, override.id, es.KEY_FREE_MONTHLY, 10)
    grant_admin(db, unlimited.id, es.KEY_UNLIMITED, True)
    grant_admin(db, both.id, es.KEY_UNLIMITED, True)
    grant_admin(db, both.id, es.KEY_DAILY_LIMIT, 2)
    es.grant(db, user_id=expired.id, key=es.KEY_UNLIMITED, value=True, source="admin_grant",
             expires_at=datetime.now(timezone.utc) - timedelta(minutes=5))
    db.commit()
    # statuses: free = active (workout today), credits = active (scan), override = active (login),
    # unlimited = inactive (never), both = deleted, expired = purge-eligible
    _session(db, free.id, TODAY)
    db.add(ScreenshotUsage(user_id=credits.id, screenshots_count=1))
    override.last_login_at = datetime.now(timezone.utc) - timedelta(days=2)
    both.is_deleted, both.deleted_at = True, datetime.now(timezone.utc) - timedelta(days=2)
    expired.is_deleted, expired.deleted_at = True, datetime.now(timezone.utc) - timedelta(days=60)
    db.commit()
    return {
        "tag": tag, "free": free, "credits": credits, "override": override,
        "unlimited": unlimited, "both": both, "expired": expired,
    }


ALL_STATUSES = "active,inactive,deleted,purge_eligible"


class TestListUsersV2:
    """Console v2 §6.2: ``status`` / ``plan`` / ``joined_days``, the new sort keys, SQL == ``plans_for``."""

    def _rows(self, client, headers, **params):
        response = client.get("/admin/users", headers=headers, params=params)
        assert response.status_code == 200, response.text
        body = response.json()
        assert_no_secret_keys(body)
        return body["items"], body["total"]

    def test_rows_carry_plan_and_status(self, client, admin_headers, plan_cohort):
        headers, _ = admin_headers(email="owner-v2rows@example.com")
        rows, total = self._rows(client, headers, q=plan_cohort["tag"], status=ALL_STATUSES)
        assert total == 6
        by_id = {r["id"]: r for r in rows}
        c = plan_cohort
        assert by_id[c["free"].id]["plan"] == "free" and by_id[c["free"].id]["status"] == "active"
        assert by_id[c["free"].id]["last_active_kind"] == "workout"
        assert by_id[c["credits"].id]["plan"] == "credits" and by_id[c["credits"].id]["last_active_kind"] == "scan"
        assert by_id[c["credits"].id]["purchased_credits"] == 30
        assert by_id[c["credits"].id]["scans_4wk"] == 1
        assert by_id[c["override"].id]["plan"] == "override" and by_id[c["override"].id]["free_monthly"] == 10
        assert by_id[c["override"].id]["override_keys"] == [es.KEY_FREE_MONTHLY]  # the row chip lists them (v2.3)
        assert by_id[c["free"].id]["override_keys"] == []
        assert by_id[c["both"].id]["override_keys"] == [es.KEY_DAILY_LIMIT]  # kept under Unlimited (§3.1)
        assert by_id[c["override"].id]["last_active_kind"] == "login" and by_id[c["override"].id]["status"] == "active"
        assert by_id[c["unlimited"].id]["plan"] == "unlimited" and by_id[c["unlimited"].id]["plan_source"] == "admin_grant"
        assert by_id[c["unlimited"].id]["status"] == "inactive" and by_id[c["unlimited"].id]["last_active"] is None
        assert by_id[c["both"].id]["plan"] == "unlimited" and by_id[c["both"].id]["status"] == "deleted"
        assert by_id[c["expired"].id]["plan"] == "free" and by_id[c["expired"].id]["status"] == "purge_eligible"
        assert by_id[c["expired"].id]["plan_expires_at"] is None

    def test_status_and_plan_filters(self, client, admin_headers, plan_cohort):
        headers, _ = admin_headers(email="owner-v2filters@example.com")
        c, tag = plan_cohort, plan_cohort["tag"]
        ids = lambda **p: {r["id"] for r in self._rows(client, headers, q=tag, **p)[0]}  # noqa: E731
        assert ids() == {c["free"].id, c["credits"].id, c["override"].id, c["unlimited"].id}  # default: not deleted
        assert ids(status="active") == {c["free"].id, c["credits"].id, c["override"].id}
        assert ids(status="inactive") == {c["unlimited"].id}
        assert ids(status="deleted") == {c["both"].id}
        assert ids(status="purge_eligible") == {c["expired"].id}
        assert ids(status="deleted,purge_eligible") == {c["both"].id, c["expired"].id}
        assert ids(plan="free") == {c["free"].id}
        assert ids(plan="unlimited", status=ALL_STATUSES) == {c["unlimited"].id, c["both"].id}
        assert ids(plan="credits,override") == {c["credits"].id, c["override"].id}
        # the W4 exit criterion (§7.1)
        assert ids(status="purge_eligible", plan="free") == {c["expired"].id}
        assert ids(joined_days=7) == ids()
        assert client.get("/admin/users", headers=headers, params={"status": "zombie"}).status_code == 422
        assert client.get("/admin/users", headers=headers, params={"plan": "gold"}).status_code == 422
        assert client.get("/admin/users", headers=headers, params={"joined_days": 0}).status_code == 422

    def test_v1_params_still_map(self, client, admin_headers, plan_cohort):
        headers, _ = admin_headers(email="owner-v2legacy@example.com")
        c, tag = plan_cohort, plan_cohort["tag"]
        ids = lambda **p: {r["id"] for r in self._rows(client, headers, q=tag, **p)[0]}  # noqa: E731
        assert ids(deleted="true") == {c["both"].id, c["expired"].id}
        assert ids(deleted="false") == ids()
        assert ids(unlimited="true") == {c["unlimited"].id}
        assert ids(unlimited="false") == {c["free"].id, c["credits"].id, c["override"].id}
        assert ids(status="deleted", deleted="false") == {c["both"].id}  # explicit v2 wins

    def test_sql_plan_and_status_sort_match_the_python_models(self, client, db, admin_headers, plan_cohort):
        headers, _ = admin_headers(email="owner-v2sort@example.com")
        rows, _ = self._rows(client, headers, q=plan_cohort["tag"], status=ALL_STATUSES, sort="plan", order="asc")
        plans = [r["plan"] for r in rows]
        assert plans == sorted(plans, key=es.PLAN_ORDER.index)
        assert {plans.count(p) for p in es.PLAN_ORDER} == {2, 1}  # every plan present
        expected = es.plans_for(db, [r["id"] for r in rows])
        assert [expected[r["id"]].plan for r in rows] == plans

        rows, _ = self._rows(client, headers, q=plan_cohort["tag"], status=ALL_STATUSES, sort="status", order="asc")
        statuses = [r["status"] for r in rows]
        assert statuses == sorted(statuses, key=admin_read_service.STATUS_ORDER.index)
        assert set(statuses) == set(admin_read_service.STATUS_ORDER)
        # the SQL filter agrees with the displayed value for every bucket
        for status in admin_read_service.STATUS_ORDER:
            bucket, _ = self._rows(client, headers, q=plan_cohort["tag"], status=status)
            assert {r["status"] for r in bucket} <= {status}
        for plan in es.PLAN_ORDER:
            bucket, _ = self._rows(client, headers, q=plan_cohort["tag"], status=ALL_STATUSES, plan=plan)
            assert {r["plan"] for r in bucket} <= {plan}

    @pytest.mark.parametrize("sort,key", [
        ("last_active", "last_active"), ("scans_4wk", "scans_4wk"), ("level", "level"),
        ("created_at", "created_at"), ("created", "created_at"), ("email", "email"),
        ("session_count", "session_count"),  # the Sessions header (§4.3, v2.3)
    ])
    def test_new_sort_keys(self, client, admin_headers, plan_cohort, sort, key):
        headers, _ = admin_headers(email=f"owner-v2sort-{sort}@example.com")
        rows, _ = self._rows(client, headers, q=plan_cohort["tag"], status=ALL_STATUSES, sort=sort, order="desc")
        values = [r[key] for r in rows if r[key] is not None]
        assert values == sorted(values, reverse=True)
        nulls = [r[key] for r in rows if r[key] is None]
        assert rows[len(rows) - len(nulls):] == [r for r in rows if r[key] is None]  # nulls last

    def test_id_substring_search(self, client, admin_headers, plan_cohort):
        headers, _ = admin_headers(email="owner-v2id@example.com")
        target = plan_cohort["free"]
        rows, total = self._rows(client, headers, q=target.id[-8:])
        assert target.id in {r["id"] for r in rows}


class TestUserDetail:
    BLOCKS = {
        "user", "profile", "progress", "balance", "entitlements", "effective_limits", "campaign",
        "integrations", "data_health", "preview", "recent_audit", "usage",
        "plan", "account", "scans", "activity",  # console v2 §6.3
    }

    def test_fresh_user_renders_every_block(self, client, admin_headers, create_test_user):
        headers, _ = admin_headers(email="owner-fresh@example.com")
        fresh, _ = create_test_user(email="fresh-detail@example.com")
        response = client.get(f"/admin/users/{fresh.id}", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == self.BLOCKS
        assert_no_secret_keys(body)
        assert body["user"]["id"] == fresh.id and body["user"]["email"] == fresh.email
        assert body["user"]["purge_eligible_at"] is None
        assert body["profile"]["preferred_unit"] == "lb"
        assert body["progress"]["level"] == 1
        assert body["balance"] == {
            "exists": False, "scan_credits": None, "has_unlimited": False,
            "free_scans_reset_at": None, "purchases": [],
        }
        assert body["entitlements"] == []
        assert body["effective_limits"]["defaults"]["free_monthly"] == body["effective_limits"]["free_monthly"]
        assert body["campaign"] is None
        assert body["integrations"]["whoop"] == {
            "connected": False, "last_synced_at": None, "token_expires_at": None, "scope": None,
        }
        assert body["integrations"]["active_device_tokens"] == 0
        assert body["data_health"]["sessions_total"] == 0
        assert body["preview"]["hunt"] is None
        assert body["preview"]["today"] == TODAY.isoformat()
        assert body["preview"]["scan_balance"] == {"scan_credits": 0, "has_unlimited": False}
        assert 0 <= body["preview"]["condition"]["score"] <= 100
        assert body["recent_audit"] == []
        assert body["usage"]["user_id"] == fresh.id and body["usage"]["sessions_by_week"] == []
        assert response.headers["cache-control"] == "no-store"
        # A read never creates a balance row.
        assert client.get(f"/admin/users/{fresh.id}", headers=headers).json()["balance"]["exists"] is False

    def test_rich_user_blocks_and_no_token_material(self, client, db, admin_headers, create_test_user):
        headers, owner = admin_headers(email="owner-rich@example.com")
        user, _ = create_test_user(email="rich-detail@example.com")
        _session(db, user.id, TODAY - timedelta(days=2))
        db.add(ScanBalance(user_id=user.id, scan_credits=7, has_unlimited=False))
        db.add(PurchaseRecord(
            user_id=user.id, product_id="com.nickchua.fitnessapp.scan_20",
            transaction_id="1000000123", credits_added=20, purchase_type="consumable",
            verified=True, environment="Sandbox", original_transaction_id="1000000123",
            purchase_date=datetime(2026, 9, 10, 8, 0),
        ))
        db.add(PurchaseRecord(
            user_id=user.id, product_id="com.nickchua.fitnessapp.scan_50",
            transaction_id="1000000124", credits_added=50, purchase_type="consumable",
        ))
        db.add(DeviceToken(user_id=user.id, token=f"apns-{uuid.uuid4().hex}", is_active=True))
        db.add(DeviceToken(user_id=user.id, token=f"apns-{uuid.uuid4().hex}", is_active=False))
        db.add(Exercise(name="Custom Thing", is_custom=True, user_id=user.id, family_id=None))
        whoop = WhoopConnection(
            user_id=user.id, scope="read:workout read:recovery",
            last_synced_at=datetime(2026, 9, 1, 12, 0),
        )
        whoop.access_token = "plain-whoop-access-secret"
        whoop.refresh_token = "plain-whoop-refresh-secret"
        db.add(whoop)
        db.commit()
        grant_admin(db, user.id, es.KEY_UNLIMITED, True)
        grant_admin(db, user.id, es.KEY_DAILY_LIMIT, 3)
        db.commit()
        from app.services.audit_service import audit
        audit(db, actor=owner, action="test.touch", target_type="user", target_id=user.id,
              after={"note": 1}, reason="seed")
        db.commit()

        response = client.get(f"/admin/users/{user.id}", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert_no_secret_keys(body)
        text = response.text
        assert "plain-whoop-access-secret" not in text
        assert "plain-whoop-refresh-secret" not in text
        assert whoop.access_token_encrypted not in text
        assert user.password_hash not in text

        assert body["balance"]["exists"] is True
        assert body["balance"]["scan_credits"] == 7
        assert body["balance"]["has_unlimited"] is True  # grant synced the cached flag
        purchases = {p["transaction_id"]: p for p in body["balance"]["purchases"]}
        assert set(purchases) == {"1000000123", "1000000124"}
        # §6.5 read surface: verification provenance, never the JWS or its payload.
        assert purchases["1000000123"]["verified"] is True
        assert purchases["1000000123"]["environment"] == "Sandbox"
        assert purchases["1000000124"]["verified"] is False
        assert purchases["1000000124"]["environment"] is None
        assert "original_transaction_id" not in purchases["1000000123"]
        keys = {e["key"]: e for e in body["entitlements"]}
        assert keys[es.KEY_UNLIMITED]["active"] is True and keys[es.KEY_UNLIMITED]["source"] == "admin_grant"
        assert body["effective_limits"]["daily_limit"] == 3
        assert body["integrations"]["whoop"]["connected"] is True
        assert body["integrations"]["whoop"]["scope"] == "read:workout read:recovery"
        assert body["integrations"]["active_device_tokens"] == 1
        assert body["data_health"]["sessions_total"] == 1
        assert body["data_health"]["custom_exercises"] == 1
        assert body["data_health"]["custom_exercises_without_family"] == 1
        assert [row["action"] for row in body["recent_audit"]] == ["test.touch"]
        assert body["recent_audit"][0]["actor_user_id"] == owner.id
        assert body["usage"]["kinds"] == {"other": 1}

    def test_detail_writes_nothing(self, client, db, admin_headers, create_test_user):
        """A read must not create progress/balance/load rows — for a fresh user,
        for a user with history, and for a soft-deleted one (spec §9.3)."""
        headers, _ = admin_headers(email="owner-ro@example.com")
        fresh, _ = create_test_user(email="ro-fresh@example.com")
        active, _ = create_test_user(email="ro-active@example.com")
        _session(db, active.id, TODAY - timedelta(days=1))
        gone, _ = create_test_user(email="ro-gone@example.com")
        gone.is_deleted = True
        gone.deleted_at = datetime.now(timezone.utc)
        db.commit()
        before = _row_counts(db)
        for user in (fresh, active, gone):
            assert client.get(f"/admin/users/{user.id}", headers=headers).status_code == 200
        db.expire_all()
        assert _row_counts(db) == before

    def test_preview_load_serves_stored_series_without_recompute(self, db, create_test_user):
        user, _ = create_test_user(email="ro-load@example.com")
        _session(db, user.id, TODAY - timedelta(days=2))
        yesterday = TODAY - timedelta(days=1)
        get_load_state(db, user.id, yesterday)  # the app's own read computes through yesterday
        assert db.query(DailyTrainingLoad).filter_by(user_id=user.id, local_date=TODAY).first() is None

        detail = admin_read_service.get_user_detail(db, user, today=TODAY)
        assert detail.preview.load.as_of == yesterday.isoformat()  # newest stored row, not recomputed
        assert db.query(DailyTrainingLoad).filter_by(user_id=user.id, local_date=TODAY).first() is None
        assert detail.progress.level == 1
        assert db.query(UserProgress).filter_by(user_id=user.id).count() == 0

    def test_campaign_and_todays_hunt(self, client, db, admin_headers, create_test_user):
        headers, _ = admin_headers(email="owner-campaign@example.com")
        user, _ = create_test_user(email="campaign-detail@example.com")
        campaign, warnings = import_plan(db, user.id, start=MONDAY)
        assert warnings == []
        start = max(MONDAY, TODAY)
        hunts = materialize_range(db, user.id, start, start + timedelta(days=6), today=start)
        db.commit()
        planned = next(h for h in hunts if h.status == "planned")

        detail = admin_read_service.get_user_detail(db, user, today=planned.date)
        assert detail.campaign is not None
        assert detail.campaign.id == campaign.id and detail.campaign.arcs == 3
        assert detail.campaign.next_planned_hunt == planned.date.isoformat()
        assert detail.preview.hunt is not None
        assert detail.preview.hunt.id == planned.id
        assert detail.preview.hunt.title == planned.template.title
        assert detail.preview.hunt.system_line

        body = client.get(f"/admin/users/{user.id}", headers=headers).json()
        assert body["campaign"]["name"] == campaign.name
        assert body["campaign"]["status"] == "active"
        assert_no_secret_keys(body)

    def test_datetimes_serialize_as_utc(self, client, admin_headers, create_test_user):
        headers, _ = admin_headers(email="owner-utc@example.com")
        user, _ = create_test_user(email="utc-detail@example.com")
        body = client.get(f"/admin/users/{user.id}", headers=headers).json()
        assert body["user"]["created_at"].endswith("Z")
        row = client.get("/admin/users", headers=headers, params={"q": user.email}).json()["items"][0]
        assert row["created_at"].endswith("Z")

    def test_deleted_user_shows_purge_date(self, client, db, admin_headers, create_test_user, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "PURGE_GRACE_DAYS", 30)
        headers, _ = admin_headers(email="owner-del@example.com")
        user, _ = create_test_user(email="deleted-detail@example.com")
        user.is_deleted = True
        user.deleted_at = datetime(2026, 8, 1, 0, 0)
        db.commit()
        body = client.get(f"/admin/users/{user.id}", headers=headers).json()
        assert body["user"]["is_deleted"] is True
        assert body["user"]["purge_eligible_at"].startswith("2026-08-31")

    def test_unknown_user_404(self, client, admin_headers):
        headers, _ = admin_headers(email="owner-404@example.com")
        response = client.get("/admin/users/nope", headers=headers)
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"


class TestUserDetailV2:
    """Console v2 §6.3: the plan / account / scans blocks and the merged activity list."""

    def test_blocks_on_a_fresh_user(self, client, admin_headers, create_test_user):
        headers, _ = admin_headers(email="owner-v2fresh@example.com")
        fresh, _ = create_test_user(email="v2-fresh@example.com")
        body = client.get(f"/admin/users/{fresh.id}", headers=headers).json()
        assert body["plan"]["plan"] == "free" and body["plan"]["last_change"] is None
        assert body["plan"]["scan_credits"] is None and body["plan"]["override_keys"] == []
        assert body["account"]["status"] == "inactive" and body["account"]["last_active"] is None
        assert body["account"]["last_login_at"] is None and body["account"]["purge_at"] is None
        assert body["account"]["token_version"] == 0
        assert body["scans"]["used_7d"] == 0 and body["scans"]["today_count"] == 0
        assert body["scans"]["daily_limit"] == body["effective_limits"]["daily_limit"]
        assert body["activity"] == []

    def test_login_stamps_last_login_and_the_activity_list_is_newest_first(
        self, client, db, admin_headers, create_test_user, seed_scan_balance
    ):
        headers, owner = admin_headers(email="owner-v2activity@example.com")
        user, pwd = create_test_user(email="v2-active@example.com")
        assert client.post("/auth/login", json={"email": user.email, "password": pwd}).status_code == 200
        db.expire_all()
        assert user.last_login_at is not None
        _session(db, user.id, TODAY - timedelta(days=3))
        db.add(ScreenshotUsage(user_id=user.id, screenshots_count=2,
                               created_at=datetime.now(timezone.utc) - timedelta(days=1)))
        seed_scan_balance(user.id, credits=1)
        db.commit()
        grant = client.post(f"/admin/users/{user.id}/entitlements", headers=headers,
                            json={"key": es.KEY_DAILY_LIMIT, "value": 4, "reason": "cap for a test"})
        assert grant.status_code == 201

        body = client.get(f"/admin/users/{user.id}", headers=headers).json()
        assert_no_secret_keys(body)
        assert body["account"]["status"] == "active"
        # last_login_at is a UTC instant; its day is the UTC day, not the local TODAY
        utc_today = datetime.now(timezone.utc).date()
        assert body["account"]["last_active"] == utc_today.isoformat() and body["account"]["last_active_kind"] == "login"
        assert body["account"]["last_login_at"].endswith("Z")
        assert body["plan"]["plan"] == "override" and body["plan"]["override_keys"] == [es.KEY_DAILY_LIMIT]
        assert body["plan"]["last_change"]["action"] == "entitlement.grant"
        assert body["plan"]["last_change"]["actor"] == owner.id and body["plan"]["last_change"]["audit_id"]
        assert body["scans"]["used_7d"] == 1 and body["scans"]["used_4wk"] == 1 and body["scans"]["today_count"] == 0
        assert body["scans"]["daily_limit"] == 4 and body["scans"]["scan_credits"] == 1

        kinds = [row["kind"] for row in body["activity"]]
        assert set(kinds) == {"audit", "session", "scan", "login"}
        ats = [row["at"] for row in body["activity"]]
        assert ats == sorted(ats, reverse=True)
        audit_row = next(r for r in body["activity"] if r["kind"] == "audit")
        assert audit_row["audit_id"] and audit_row["actor"] == owner.id and audit_row["summary"] == "entitlement.grant"
        assert next(r for r in body["activity"] if r["kind"] == "scan")["summary"] == "Scan · 2 screenshots"

    def test_activity_caps_at_twenty(self, client, db, admin_headers, create_test_user):
        headers, _ = admin_headers(email="owner-v2cap@example.com")
        user, _ = create_test_user(email="v2-cap@example.com")
        for i in range(25):
            db.add(ScreenshotUsage(user_id=user.id, screenshots_count=1,
                                   created_at=datetime.now(timezone.utc) - timedelta(hours=i)))
        db.commit()
        body = client.get(f"/admin/users/{user.id}", headers=headers).json()
        assert len(body["activity"]) == 20 and body["scans"]["used_7d"] == 25

    def test_deleted_user_account_block(self, client, db, admin_headers, create_test_user):
        headers, _ = admin_headers(email="owner-v2deleted@example.com")
        user, _ = create_test_user(email="v2-deleted@example.com")
        user.is_deleted, user.deleted_at = True, datetime.now(timezone.utc) - timedelta(days=2)
        db.commit()
        body = client.get(f"/admin/users/{user.id}", headers=headers).json()
        assert body["account"]["status"] == "deleted"
        assert body["account"]["purge_at"] == body["user"]["purge_eligible_at"]


class TestProducts:
    def test_lists_seeded_catalog(self, client, admin_headers):
        headers, _ = admin_headers(email="owner-products@example.com")
        response = client.get("/admin/products", headers=headers)
        assert response.status_code == 200
        rows = response.json()
        ids: Set[str] = {row["id"] for row in rows}
        assert {spec["id"] for spec in es.DEFAULT_PRODUCTS} <= ids
        assert [row["sort_order"] for row in rows] == sorted(row["sort_order"] for row in rows)
        unlimited = next(row for row in rows if row["id"] == es.UNLIMITED_PRODUCT_ID)
        assert unlimited["entitlement_key"] == es.KEY_UNLIMITED and unlimited["active"] is True
        assert set(rows[0]) == {
            "id", "kind", "credits", "entitlement_key", "display_name", "active", "sort_order",
            "created_at", "updated_at", "sold", "sold_verified",
        }


class TestLifecycle:
    """Soft-delete / restore (spec §8.1, §16)."""

    def test_soft_delete_locks_the_user_out_and_restore_lets_them_back_in(
        self, client, db, admin_pair, step_up_body
    ):
        headers, actor, user, pwd = admin_pair("life")
        login = client.post("/auth/login", json={"email": user.email, "password": pwd}).json()
        access = {"Authorization": f"Bearer {login['access_token']}"}
        refresh = {"refresh_token": login["refresh_token"]}
        assert client.get("/profile", headers=access).status_code == 200

        deleted = client.post(f"/admin/users/{user.id}/delete", json=step_up_body(reason="spam account"), headers=headers)
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["id"] == user.id and deleted.json()["is_deleted"] is True
        assert deleted.json()["deleted_at"] is not None
        assert client.get("/profile", headers=access).status_code == 401  # the next request
        assert client.post("/auth/login", json={"email": user.email, "password": pwd}).status_code == 403
        assert client.post("/auth/refresh", json=refresh).status_code != 200
        listed = client.get("/admin/users", headers=headers, params={"deleted": True}).json()
        assert user.id in {row["id"] for row in listed["items"]}
        db.expire_all()
        version = user.token_version

        restored = client.post(f"/admin/users/{user.id}/restore", json=step_up_body(reason="false alarm"), headers=headers)
        assert restored.status_code == 200, restored.text
        assert restored.json() == {"id": user.id, "is_deleted": False, "deleted_at": None}
        db.expire_all()
        assert user.token_version == version + 1
        assert client.post("/auth/login", json={"email": user.email, "password": pwd}).status_code == 200
        assert client.post("/auth/refresh", json=refresh).status_code == 401  # pre-deletion token
        assert client.get("/profile", headers=access).status_code == 401

        rows = db.query(AdminAuditLog).filter(AdminAuditLog.target_id == user.id).order_by(AdminAuditLog.created_at).all()
        assert [r.action for r in rows] == ["user.soft_delete", "user.restore"]
        assert rows[0].before["is_deleted"] is False and rows[0].after["is_deleted"] is True
        assert rows[1].after["token_version"] == version + 1 and rows[1].actor_user_id == actor.id

    def test_409_on_state_mismatch(self, client, db, admin_pair, step_up_body):
        headers, _, user, _ = admin_pair("life")
        assert client.post(f"/admin/users/{user.id}/restore", json=step_up_body(), headers=headers).status_code == 409
        assert client.post(f"/admin/users/{user.id}/delete", json=step_up_body(), headers=headers).status_code == 200
        assert client.post(f"/admin/users/{user.id}/delete", json=step_up_body(), headers=headers).status_code == 409
        assert db.query(AdminAuditLog).filter(AdminAuditLog.target_id == user.id).count() == 1

    def test_self_and_other_admins_are_refused(self, client, db, admin_pair, admin_user, step_up_body):
        headers, actor, _, _ = admin_pair("life")
        other, _ = admin_user(email=f"life-other-admin-{uuid.uuid4().hex[:8]}@example.com")
        assert client.post(f"/admin/users/{actor.id}/delete", json=step_up_body(), headers=headers).status_code == 403
        assert client.post(f"/admin/users/{other.id}/delete", json=step_up_body(), headers=headers).status_code == 403
        other.is_deleted = True
        other.deleted_at = datetime.now(timezone.utc)
        db.commit()
        assert client.post(f"/admin/users/{other.id}/restore", json=step_up_body(), headers=headers).status_code == 403
        assert db.query(AdminAuditLog).filter(AdminAuditLog.target_id.in_([actor.id, other.id]),
                                              AdminAuditLog.action != "session.create").count() == 0

    def test_short_reason_and_unknown_user(self, client, admin_pair, step_up_body):
        headers, _, user, _ = admin_pair("life")
        assert client.post(f"/admin/users/{user.id}/delete", json=step_up_body(reason="no"), headers=headers).status_code == 422
        assert client.post("/admin/users/nope/delete", json=step_up_body(), headers=headers).status_code == 404
