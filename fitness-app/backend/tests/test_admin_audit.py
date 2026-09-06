"""Audit log (spec §5): the helper, the read route, and one row per mutation."""
import enum
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.admin import AdminAuditLog
from app.models.scan_balance import ScanBalance
from app.services import admin_service
from app.services.audit_service import audit, body_hash, scrub, snapshot
from tests.helpers_admin import MUTATIONS, MutationContext, assert_no_secret_keys, drive


class _Kind(str, enum.Enum):
    A = "a"


class _Obj:
    when = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
    kind = _Kind.A
    n = 3
    password_hash = "secret"


class TestAudit:
    def test_flush_not_commit_rolls_back_with_caller(self, db, admin_user):
        user, _ = admin_user(email="audit-rb@example.com")
        audit(db, actor=user, action="test.noop", target_type="user", target_id=user.id)
        assert db.query(AdminAuditLog).filter(AdminAuditLog.action == "test.noop").count() == 1
        db.rollback()
        assert db.query(AdminAuditLog).filter(AdminAuditLog.action == "test.noop").count() == 0

    def test_row_fields_persist_after_commit(self, db, admin_user):
        user, _ = admin_user(email="audit-row@example.com")
        row = audit(
            db, actor=user, action="credits.adjust", target_type="user", target_id="u-1",
            before={"scan_credits": 3}, after={"scan_credits": 8}, reason="because",
            idempotency_key="k1", body_sha256="h",
        )
        db.commit()
        db.expire_all()
        saved = db.query(AdminAuditLog).filter(AdminAuditLog.id == row.id).one()
        assert saved.actor_user_id == user.id
        assert saved.before == {"scan_credits": 3} and saved.after == {"scan_credits": 8}
        assert saved.reason == "because"
        assert saved.request_id is None  # outside a request scope
        assert saved.created_at is not None

    def test_system_actor_is_null(self, db):
        row = audit(db, actor=None, action="maintenance.purge_sweep", target_type="system")
        assert row.actor_user_id is None

    def test_scrub_drops_denylisted_keys_recursively(self):
        out = scrub({
            "password_hash": "x", "whoop_token": "y", "email": "a@b.example",
            "nested": {"access_token_encrypted": 1, "ok": 2}, "keep": [1, {"secret": 0, "fine": 1}],
        })
        assert out == {"nested": {"ok": 2}, "keep": [1, {"fine": 1}]}

    def test_snapshot_serializes_and_scrubs(self):
        out = snapshot(_Obj(), ["when", "kind", "n", "password_hash"])
        assert out == {"when": "2026-09-05T12:00:00+00:00", "kind": "a", "n": 3}

    def test_body_hash_is_stable_and_order_insensitive(self):
        assert body_hash({"a": 1, "b": [1, 2]}) == body_hash({"b": [1, 2], "a": 1})
        assert body_hash({"a": 1}) != body_hash({"a": 2})

    def test_idempotency_key_unique_per_actor_but_nulls_are_free(self, db, admin_user):
        user, _ = admin_user(email="audit-idem@example.com")
        audit(db, actor=user, action="credits.adjust", target_type="user", idempotency_key="dup")
        audit(db, actor=user, action="credits.adjust", target_type="user")
        audit(db, actor=user, action="credits.adjust", target_type="user")
        db.commit()
        with pytest.raises(IntegrityError):
            audit(db, actor=user, action="credits.adjust", target_type="user", idempotency_key="dup")
            db.commit()
        db.rollback()


class TestScrubAllowList:
    def test_token_version_survives_scrub(self):
        out = scrub({"token_version": 3, "refresh_token": "x"})
        assert out == {"token_version": 3}


@pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"),
    reason="append-only trigger is Postgres-only; set TEST_POSTGRES_URL to run",
)
def test_postgres_trigger_rejects_update_and_delete():
    """Run the admin_schema migration against a real Postgres and prove the
    BEFORE UPDATE OR DELETE trigger raises."""
    import sqlalchemy as sa

    from app.core.database import Base
    from tests.helpers_migrations import run_migration

    engine = sa.create_engine(os.environ["TEST_POSTGRES_URL"])
    Base.metadata.create_all(engine)
    run_migration(engine, "admin_schema", "upgrade")
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO admin_audit_log (id, action, target_type, created_at) "
            "VALUES ('pg-1', 'test', 'system', now())"
        ))
    for stmt in (
        "UPDATE admin_audit_log SET reason = 'edited' WHERE id = 'pg-1'",
        "DELETE FROM admin_audit_log WHERE id = 'pg-1'",
    ):
        with pytest.raises(Exception, match="append-only"):
            with engine.begin() as conn:
                conn.execute(sa.text(stmt))


class TestAuditRead:
    """``GET /admin/audit`` — the only route under /admin/audit (spec §5, §13)."""

    def test_lists_newest_first_with_filters_and_paging(self, client, db, admin_headers):
        headers, owner = admin_headers(email="audit-read@example.com")
        target = f"target-{uuid.uuid4().hex[:8]}"
        first = audit(db, actor=owner, action="credits.adjust", target_type="user",
                      target_id=target, before={"scan_credits": 1}, after={"scan_credits": 4},
                      reason="first")
        db.commit()
        second = audit(db, actor=owner, action="entitlement.grant", target_type="user",
                       target_id=target, reason="second")
        audit(db, actor=None, action="maintenance.purge_sweep", target_type="system")
        db.commit()

        response = client.get("/admin/audit", headers=headers, params={"target_id": target})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 2
        assert [row["id"] for row in body["items"]] == [second.id, first.id]
        row = body["items"][1]
        assert row["before"] == {"scan_credits": 1} and row["after"] == {"scan_credits": 4}
        assert row["reason"] == "first" and row["actor_user_id"] == owner.id
        assert set(row) == {
            "id", "actor_user_id", "action", "target_type", "target_id", "before", "after",
            "reason", "request_id", "ip", "idempotency_key", "created_at",
        }
        assert response.headers["cache-control"] == "no-store"

        by_action = client.get("/admin/audit", headers=headers,
                               params={"action": "credits.adjust", "target_id": target}).json()
        assert [r["id"] for r in by_action["items"]] == [first.id]
        by_actor = client.get("/admin/audit", headers=headers,
                              params={"actor_user_id": owner.id, "target_type": "user"}).json()
        assert {r["id"] for r in by_actor["items"]} >= {first.id, second.id}
        system = client.get("/admin/audit", headers=headers, params={"target_type": "system"}).json()
        assert all(r["actor_user_id"] is None for r in system["items"])

        page = client.get("/admin/audit", headers=headers,
                          params={"target_id": target, "limit": 1, "offset": 1}).json()
        assert page["total"] == 2 and [r["id"] for r in page["items"]] == [first.id]

    def test_session_create_row_carries_request_id_and_ip(self, client, admin_user):
        user, pwd = admin_user(email="audit-sess@example.com")
        minted = client.post("/admin/session", json={"email": user.email, "password": pwd},
                             headers={"X-Request-ID": "audit-req-42",
                                      "X-Forwarded-For": "198.51.100.7"})
        token = minted.json()["admin_token"]
        rows = client.get("/admin/audit", headers={"Authorization": f"Bearer {token}"},
                          params={"actor_user_id": user.id, "action": "session.create"}).json()
        assert rows["total"] == 1
        assert rows["items"][0]["request_id"] == "audit-req-42"
        assert rows["items"][0]["ip"] == "198.51.100.7"
        assert rows["items"][0]["target_id"] == user.id

    def test_only_get_is_routed(self, client, admin_headers):
        headers, _ = admin_headers(email="audit-methods@example.com")
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert client.request(method, "/admin/audit", headers=headers).status_code == 405


class TestAuditMutations:
    """Every mutation route writes exactly one row, in the same transaction (spec §5, §16)."""

    @pytest.mark.parametrize("case", MUTATIONS, ids=[c.name for c in MUTATIONS])
    def test_one_row_with_request_id_ip_reason_and_no_secrets(self, client, db, admin_pair, case):
        headers, actor, target, _ = admin_pair("audit")
        ctx = MutationContext(db=db, actor=actor, target=target, password="TestPass123!")
        request_id = f"req-{ctx.tag}"

        response, call = drive(
            client, headers, case, ctx, **{"X-Request-ID": request_id, "X-Forwarded-For": "198.51.100.9"}
        )
        assert response.status_code == call.expect, (case.name, response.text)
        rows = db.query(AdminAuditLog).filter(AdminAuditLog.request_id == request_id).all()
        assert len(rows) == 1, [r.action for r in rows]
        row = rows[0]
        assert row.action == case.action and row.actor_user_id == actor.id
        assert row.ip == "198.51.100.9" and row.reason
        assert_no_secret_keys({"before": row.before, "after": row.after})
        assert_no_secret_keys(response.json())

    def test_failure_after_audit_rolls_back_the_change_and_the_row(
        self, client, db, admin_headers, create_test_user, seed_scan_balance, monkeypatch
    ):
        headers, _ = admin_headers(email="audit-boom-admin@example.com")
        target, _ = create_test_user(email="audit-boom-target@example.com")
        seed_scan_balance(target.id, credits=3)
        real_audit = admin_service.audit

        def audit_then_fail(*args, **kwargs):
            real_audit(*args, **kwargs)
            raise RuntimeError("after audit()")

        monkeypatch.setattr(admin_service, "audit", audit_then_fail)
        response = client.post(
            f"/admin/users/{target.id}/credits", json={"delta": 5, "reason": "boom"},
            headers={**headers, "Idempotency-Key": "boom-key", "X-Request-ID": "req-boom"},
        )
        assert response.status_code == 500
        db.rollback()  # what ``get_db``'s close() does for the failed request
        assert db.query(AdminAuditLog).filter(AdminAuditLog.request_id == "req-boom").count() == 0
        db.expire_all()
        assert db.query(ScanBalance).filter(ScanBalance.user_id == target.id).one().scan_credits == 3
