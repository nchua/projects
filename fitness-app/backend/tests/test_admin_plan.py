"""
Change plan (console v2 spec §3.2, §5.2, §6.4, §7.2): ``POST /admin/users/{id}/plan``
for each target, skipped / extend / shorten, the step-up rules, the
purchase-sourced guard, and the bulk route's applied / skipped / failed groups
with one transaction per user.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.admin import AdminAuditLog
from app.models.entitlement import UserEntitlement
from app.services import entitlement_service as es
from tests.helpers_admin import assert_no_secret_keys, balance_of, grant_admin

REASON = {"reason": "friend of the owner"}


def _plan(client, headers, user_id, **body):
    return client.post(f"/admin/users/{user_id}/plan", json={**REASON, **body}, headers=headers)


def _audits(db, user_id: str):
    return (
        db.query(AdminAuditLog)
        .filter(AdminAuditLog.target_id == user_id, AdminAuditLog.action == "user.plan_change")
        .order_by(AdminAuditLog.created_at, AdminAuditLog.id)
        .all()
    )


@pytest.fixture
def pair(admin_pair):
    return admin_pair("plan")


class TestSingle:
    def test_free_to_unlimited_then_skipped(self, client, db, pair):
        headers, actor, user, _ = pair
        response = _plan(client, headers, user.id, target="unlimited")
        assert response.status_code == 200, response.text
        body = response.json()
        assert_no_secret_keys(body)
        assert body["user_id"] == user.id and body["skipped"] is False and body["audit_id"]
        assert body["before"]["plan"] == "free" and body["after"]["plan"] == "unlimited"
        assert body["after"]["plan_source"] == "admin_grant" and body["after"]["expires_at"] is None
        assert balance_of(db, user.id).has_unlimited is True  # through grant → sync_unlimited_flag

        rows = _audits(db, user.id)
        assert len(rows) == 1 and rows[0].actor_user_id == actor.id
        assert rows[0].before["plan"] == "free" and rows[0].after["plan"] == "unlimited"
        assert rows[0].reason == REASON["reason"]

        again = _plan(client, headers, user.id, target="unlimited")
        assert again.status_code == 200 and again.json()["skipped"] is True
        assert again.json()["audit_id"] is None and again.json()["before"] == again.json()["after"]
        assert len(_audits(db, user.id)) == 1  # no audit row for a skip

    def test_extend_and_shorten_revoke_then_regrant(self, client, db, pair):
        headers, _, user, _ = pair
        assert _plan(client, headers, user.id, target="unlimited").status_code == 200
        later = (datetime.now(timezone.utc) + timedelta(days=30)).replace(microsecond=0)
        response = _plan(client, headers, user.id, target="unlimited", expires_at=later.isoformat())
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["skipped"] is False
        assert body["after"]["expires_at"].startswith(later.strftime("%Y-%m-%dT%H:%M:%S"))
        rows = db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).all()
        assert sorted(r.revoked_at is None for r in rows) == [False, True]  # old revoked, new active
        assert balance_of(db, user.id).has_unlimited is True
        # the same expiry again → skipped
        same = _plan(client, headers, user.id, target="unlimited", expires_at=later.isoformat())
        assert same.json()["skipped"] is True
        assert len(_audits(db, user.id)) == 2

    def test_topup_adds_purchased_credits_and_needs_step_up_above_50(self, client, db, pair, seed_scan_balance):
        headers, _, user, pwd = pair
        seed_scan_balance(user.id, credits=3)
        response = _plan(client, headers, user.id, target="topup", credits=20)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["before"]["plan"] == "free" and body["after"]["plan"] == "credits"
        assert body["after"]["scan_credits"] == 23
        assert body["after"]["purchased_credits"] == 23 - body["after"]["free_monthly"]
        assert balance_of(db, user.id).scan_credits == 23

        assert _plan(client, headers, user.id, target="topup", credits=60).status_code == 401
        assert _plan(client, headers, user.id, target="topup", credits=60, password="nope").status_code == 401
        assert balance_of(db, user.id).scan_credits == 23
        big = _plan(client, headers, user.id, target="topup", credits=60, password=pwd)
        assert big.status_code == 200, big.text
        assert balance_of(db, user.id).scan_credits == 83
        assert len(_audits(db, user.id)) == 2

    def test_topup_under_unlimited_keeps_unlimited_and_banks_the_credits(self, client, db, pair):
        headers, _, user, _ = pair
        assert _plan(client, headers, user.id, target="unlimited").status_code == 200
        body = _plan(client, headers, user.id, target="topup", credits=20).json()
        assert body["before"]["plan"] == "unlimited" and body["after"]["plan"] == "unlimited"
        assert body["after"]["scan_credits"] == body["before"]["scan_credits"] + 20

    def test_remove_unlimited_is_step_up_and_never_touches_credits(self, client, db, pair, seed_scan_balance):
        headers, _, user, pwd = pair
        seed_scan_balance(user.id, credits=42)
        assert _plan(client, headers, user.id, target="unlimited").status_code == 200
        assert _plan(client, headers, user.id, target="remove_unlimited").status_code == 401
        assert _plan(client, headers, user.id, target="remove_unlimited", password="wrong").status_code == 401
        assert balance_of(db, user.id).has_unlimited is True

        response = _plan(client, headers, user.id, target="remove_unlimited", password=pwd)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["before"]["plan"] == "unlimited" and body["after"]["plan"] == "credits"
        assert body["after"]["scan_credits"] == 42  # purchased credits belong to the hunter (§3.2)
        assert balance_of(db, user.id).has_unlimited is False
        assert balance_of(db, user.id).scan_credits == 42

        skipped = _plan(client, headers, user.id, target="remove_unlimited", password=pwd)
        assert skipped.status_code == 200 and skipped.json()["skipped"] is True

    def test_remove_lands_on_free_without_purchased_credits(self, client, db, pair):
        headers, _, user, pwd = pair
        assert _plan(client, headers, user.id, target="unlimited").status_code == 200
        body = _plan(client, headers, user.id, target="remove_unlimited", password=pwd).json()
        assert body["after"]["plan"] == "free"

    def test_exit_criterion_sequence_and_audit_trail(self, client, db, pair):
        """Free → Unlimited → Credits (top-up) → remove → Credits, with the right audit rows (§7.1)."""
        headers, _, user, pwd = pair
        seq = [
            _plan(client, headers, user.id, target="unlimited"),
            _plan(client, headers, user.id, target="topup", credits=20),
            _plan(client, headers, user.id, target="remove_unlimited", password=pwd),
        ]
        assert [r.status_code for r in seq] == [200, 200, 200], [r.text for r in seq]
        plans = [(r.json()["before"]["plan"], r.json()["after"]["plan"]) for r in seq]
        assert plans == [("free", "unlimited"), ("unlimited", "unlimited"), ("unlimited", "credits")]
        rows = _audits(db, user.id)
        assert [(r.before["plan"], r.after["plan"]) for r in rows] == plans
        assert all(r.action == "user.plan_change" for r in rows)
        detail = client.get(f"/admin/users/{user.id}", headers=headers).json()
        assert detail["plan"]["plan"] == "credits"
        assert detail["plan"]["last_change"]["audit_id"] == rows[-1].id
        assert detail["plan"]["last_change"]["action"] == "user.plan_change"

    def test_purchase_sourced_removal_survives_restore_purchases(self, client, db, pair, auth_headers):
        headers, _, _, _ = pair
        user_headers, user = auth_headers(email=f"plan-buyer-{uuid.uuid4().hex[:8]}@example.com")
        bought = client.post(
            "/scan-balance/verify-purchase", headers=user_headers,
            json={"transaction_id": str(5_000_000_000 + int(uuid.uuid4().hex[:6], 16)), "product_id": es.UNLIMITED_PRODUCT_ID},
        )
        assert bought.status_code == 200, bought.text
        before = client.get(f"/admin/users/{user.id}", headers=headers).json()["plan"]
        assert before["plan"] == "unlimited" and before["plan_source"] == "purchase"

        removed = _plan(client, headers, user.id, target="remove_unlimited", password="TestPass123!")
        assert removed.status_code == 200, removed.text
        assert removed.json()["after"]["plan"] == "free"
        restored = client.post("/scan-balance/restore-purchases", headers=user_headers)
        assert restored.status_code == 200 and restored.json()["has_unlimited"] is False
        assert client.get(f"/admin/users/{user.id}", headers=headers).json()["plan"]["plan"] == "free"

    def test_purchase_sourced_unlimited_is_never_revoked_by_target_unlimited(self, client, db, pair, auth_headers):
        """§3.2 / v1 §20: only remove_unlimited (step-up) may revoke a row the hunter paid for."""
        headers, _, _, _ = pair
        user_headers, user = auth_headers(email=f"plan-paid-{uuid.uuid4().hex[:8]}@example.com")
        bought = client.post(
            "/scan-balance/verify-purchase", headers=user_headers,
            json={"transaction_id": str(6_000_000_000 + int(uuid.uuid4().hex[:6], 16)), "product_id": es.UNLIMITED_PRODUCT_ID},
        )
        assert bought.status_code == 200, bought.text
        later = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        response = _plan(client, headers, user.id, target="unlimited", expires_at=later)
        assert response.status_code == 200, response.text
        assert response.json()["skipped"] is True and response.json()["after"]["plan_source"] == "purchase"
        rows = db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).all()
        assert len(rows) == 1 and rows[0].revoked_at is None and rows[0].source == "purchase"
        assert _audits(db, user.id) == []
        bulk = client.post("/admin/users/plan", headers=headers,
                           json={"user_ids": [user.id], "target": "unlimited", "expires_at": later, **REASON}).json()
        assert bulk["skipped"] == [{"user_id": user.id, "why": "already unlimited by purchase"}]

    def test_backfill_unlimited_is_skipped_too(self, client, db, pair):
        headers, _, user, _ = pair
        es.grant(db, user_id=user.id, key=es.KEY_UNLIMITED, value=True, source="backfill")
        db.commit()
        later = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        body = _plan(client, headers, user.id, target="unlimited", expires_at=later).json()
        assert body["skipped"] is True and body["before"]["plan_source"] == "backfill"

    def test_past_expiry_is_422(self, client, db, pair):
        headers, _, user, _ = pair
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        assert _plan(client, headers, user.id, target="unlimited", expires_at=past).status_code == 422
        assert db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).count() == 0

    def test_idempotency_key_replays_a_topup(self, client, db, pair, seed_scan_balance):
        headers, actor, user, _ = pair
        seed_scan_balance(user.id, credits=3)
        key = {"Idempotency-Key": f"topup-{uuid.uuid4().hex[:8]}"}
        first = client.post(f"/admin/users/{user.id}/plan", headers={**headers, **key},
                            json={**REASON, "target": "topup", "credits": 20})
        assert first.status_code == 200, first.text
        assert first.json()["replayed"] is False and balance_of(db, user.id).scan_credits == 23
        again = client.post(f"/admin/users/{user.id}/plan", headers={**headers, **key},
                            json={**REASON, "target": "topup", "credits": 20})
        assert again.status_code == 200, again.text
        assert again.json()["replayed"] is True and again.json()["audit_id"] == first.json()["audit_id"]
        assert again.json()["after"] == first.json()["after"]
        assert balance_of(db, user.id).scan_credits == 23  # credited once
        assert len(_audits(db, user.id)) == 1
        other = client.post(f"/admin/users/{user.id}/plan", headers={**headers, **key},
                            json={**REASON, "target": "topup", "credits": 21})
        assert other.status_code == 422
        assert balance_of(db, user.id).scan_credits == 23
        assert _audits(db, user.id)[0].idempotency_key == key["Idempotency-Key"]

    def test_validation_422s(self, client, db, pair):
        headers, _, user, _ = pair
        assert _plan(client, headers, user.id, target="topup").status_code == 422
        assert _plan(client, headers, user.id, target="topup", credits=0).status_code == 422
        assert _plan(client, headers, user.id, target="unlimited", credits=5).status_code == 422
        assert _plan(client, headers, user.id, target="topup", credits=5,
                     expires_at="2026-12-01T00:00:00Z").status_code == 422
        assert _plan(client, headers, user.id, target="downgrade").status_code == 422
        assert client.post(f"/admin/users/{user.id}/plan", json={"target": "unlimited"}, headers=headers).status_code == 422
        assert _plan(client, headers, "nope", target="unlimited").status_code == 404
        assert _audits(db, user.id) == []


class TestBulk:
    URL = "/admin/users/plan"

    def _users(self, create_test_user, n: int):
        return [create_test_user(email=f"bulk-{uuid.uuid4().hex[:8]}@example.com")[0] for _ in range(n)]

    def test_applied_skipped_failed_and_shared_request_id(self, client, db, pair, create_test_user):
        headers, actor, _, _ = pair
        a, b = self._users(create_test_user, 2)
        grant_admin(db, b.id, es.KEY_UNLIMITED, True)
        db.commit()
        request_id = f"bulk-{uuid.uuid4().hex[:8]}"
        response = client.post(
            self.URL, headers={**headers, "X-Request-ID": request_id},
            json={"user_ids": [a.id, b.id, "no-such-user"], "target": "unlimited", **REASON},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert_no_secret_keys(body)
        assert [r["user_id"] for r in body["applied"]] == [a.id]
        assert body["applied"][0]["after"]["plan"] == "unlimited"
        assert body["skipped"] == [{"user_id": b.id, "why": "already unlimited"}]
        assert body["failed"] == [{"user_id": "no-such-user", "error": "User not found"}]
        assert balance_of(db, a.id).has_unlimited is True
        rows = db.query(AdminAuditLog).filter(AdminAuditLog.request_id == request_id).all()
        assert [r.target_id for r in rows] == [a.id] and rows[0].action == "user.plan_change"

    def test_one_failure_leaves_the_others_committed(self, client, db, pair, create_test_user, monkeypatch):
        headers, _, _, _ = pair
        a, b, c = self._users(create_test_user, 3)
        from app.services import admin_mutation_service as ams

        real = ams.apply_plan_change

        def boom_on_b(db_, **kw):
            if kw["user"].id == b.id:
                raise RuntimeError("simulated failure")
            return real(db_, **kw)

        monkeypatch.setattr(ams, "apply_plan_change", boom_on_b)
        response = client.post(
            self.URL, headers=headers,
            json={"user_ids": [a.id, b.id, c.id], "target": "topup", "credits": 5, **REASON},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert [r["user_id"] for r in body["applied"]] == [a.id, c.id]
        assert body["failed"] == [{"user_id": b.id, "error": "RuntimeError: simulated failure"}]
        db.expire_all()
        assert balance_of(db, a.id).scan_credits == balance_of(db, c.id).scan_credits
        assert db.query(AdminAuditLog).filter(AdminAuditLog.target_id == b.id).count() == 0

    def test_cap_101_is_422_and_empty_is_422(self, client, pair):
        headers, _, _, _ = pair
        ids = [f"u{i}" for i in range(101)]
        assert client.post(self.URL, headers=headers, json={"user_ids": ids, "target": "unlimited", **REASON}).status_code == 422
        assert client.post(self.URL, headers=headers, json={"user_ids": [], "target": "unlimited", **REASON}).status_code == 422

    def test_step_up_once_for_remove_and_large_topup(self, client, db, pair, create_test_user):
        headers, actor, _, pwd = pair
        a, b = self._users(create_test_user, 2)
        for u in (a, b):
            grant_admin(db, u.id, es.KEY_UNLIMITED, True)
        db.commit()
        body = {"user_ids": [a.id, b.id], "target": "remove_unlimited", **REASON}
        assert client.post(self.URL, headers=headers, json=body).status_code == 401
        assert client.post(self.URL, headers=headers, json={**body, "password": "wrong"}).status_code == 401
        db.refresh(actor)
        assert actor.admin_failed_logins == 1 and balance_of(db, a.id).has_unlimited is True

        ok = client.post(self.URL, headers=headers, json={**body, "password": pwd})
        assert ok.status_code == 200, ok.text
        assert len(ok.json()["applied"]) == 2 and balance_of(db, b.id).has_unlimited is False
        db.refresh(actor)
        assert actor.admin_failed_logins == 0

        big = {"user_ids": [a.id], "target": "topup", "credits": 60, **REASON}
        assert client.post(self.URL, headers=headers, json=big).status_code == 401
        assert client.post(self.URL, headers=headers, json={**big, "password": pwd}).status_code == 200

    def test_duplicate_ids_apply_once(self, client, db, pair, create_test_user):
        headers, _, _, _ = pair
        (a,) = self._users(create_test_user, 1)
        body = client.post(self.URL, headers=headers, json={"user_ids": [a.id, a.id], "target": "topup", "credits": 5, **REASON}).json()
        assert len(body["applied"]) == 1 and balance_of(db, a.id).scan_credits == body["applied"][0]["after"]["scan_credits"]
