"""Audit helper: same-transaction rule, scrubbing, hashing, idempotency index (spec §5)."""
import enum
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.admin import AdminAuditLog
from app.services.audit_service import audit, body_hash, scrub, snapshot


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
