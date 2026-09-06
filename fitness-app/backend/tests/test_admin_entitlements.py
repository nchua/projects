"""
Entitlements, per-user scan limits, the product catalog, and the purchase
interim caps (control-plane spec §6).
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.api.screenshot import _check_screenshot_rate_limit, _reserve_scan_credits
from app.core.config import settings
from app.models.admin import AdminAuditLog
from app.models.entitlement import EntitlementSource, Product, UserEntitlement
from app.models.scan_balance import ScanBalance
from app.models.screenshot_usage import ScreenshotUsage
from app.services import entitlement_service as es
from tests.helpers_admin import grant_admin

SCAN_20 = "com.nickchua.fitnessapp.scan_20"
SCAN_50 = "com.nickchua.fitnessapp.scan_50"


def _balance(db, user_id: str) -> ScanBalance:
    db.expire_all()
    return db.query(ScanBalance).filter(ScanBalance.user_id == user_id).one()


def _verify(client, headers, txn: str, product_id: str):
    return client.post(
        "/scan-balance/verify-purchase",
        headers=headers,
        json={"transaction_id": txn, "product_id": product_id},
    )


class TestGrantRevoke:
    def test_grant_unlimited_sets_flag_and_scanner_passes_with_zero_credits(
        self, db, create_test_user, seed_scan_balance
    ):
        user, _ = create_test_user(email="ent-grant@example.com")
        seed_scan_balance(user.id, credits=0)
        row = es.grant(
            db, user_id=user.id, key=es.KEY_UNLIMITED, value=True,
            source=EntitlementSource.ADMIN_GRANT, reason="test",
        )
        db.commit()
        assert row is not None and row.source == "admin_grant"
        assert _balance(db, user.id).has_unlimited is True
        assert _reserve_scan_credits(db, user.id) is True
        assert _balance(db, user.id).scan_credits == 0  # unlimited does not deduct

    def test_revoke_clears_flag_and_scanner_fails(self, db, create_test_user, seed_scan_balance):
        user, _ = create_test_user(email="ent-revoke@example.com")
        seed_scan_balance(user.id, credits=0)
        row = es.grant(
            db, user_id=user.id, key=es.KEY_UNLIMITED, value=True, source="admin_grant"
        )
        db.commit()
        es.revoke(db, row)
        db.commit()
        assert row.revoked_at is not None
        assert _balance(db, user.id).has_unlimited is False
        assert _reserve_scan_credits(db, user.id) is False

    def test_unknown_key_and_wrong_type_raise(self, db, create_test_user):
        user, _ = create_test_user(email="ent-bad@example.com")
        with pytest.raises(ValueError):
            es.grant(db, user_id=user.id, key="beta.moon", value=True, source="admin_grant")
        with pytest.raises(ValueError):
            grant_admin(db, user.id, es.KEY_UNLIMITED, "yes")
        with pytest.raises(ValueError):
            grant_admin(db, user.id, es.KEY_DAILY_LIMIT, True)
        with pytest.raises(ValueError):
            grant_admin(db, user.id, es.KEY_DAILY_LIMIT, -1)

    def test_expired_row_is_ignored(self, db, create_test_user, seed_scan_balance):
        user, _ = create_test_user(email="ent-expired@example.com")
        seed_scan_balance(user.id, credits=0)
        es.grant(
            db, user_id=user.id, key=es.KEY_UNLIMITED, value=True, source="admin_grant",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.commit()
        assert es.is_entitled(db, user.id, es.KEY_UNLIMITED) is False
        assert _balance(db, user.id).has_unlimited is False

    def test_purchase_sourced_grant_is_noop_once_referenced(self, db, create_test_user):
        user, _ = create_test_user(email="ent-receipt@example.com")
        first = es.grant(
            db, user_id=user.id, key=es.KEY_UNLIMITED, value=True,
            source=EntitlementSource.PURCHASE, purchase_record_id="rec-1",
        )
        assert first is not None
        assert es.grant(
            db, user_id=user.id, key=es.KEY_UNLIMITED, value=True,
            source=EntitlementSource.PURCHASE, purchase_record_id="rec-1",
        ) is None
        es.revoke(db, first)
        # Revoked rows still block re-grant from the same receipt.
        assert es.grant(
            db, user_id=user.id, key=es.KEY_UNLIMITED, value=True,
            source=EntitlementSource.PURCHASE, purchase_record_id="rec-1",
        ) is None
        db.commit()
        assert es.is_entitled(db, user.id, es.KEY_UNLIMITED) is False

    def test_newest_active_row_wins(self, db, create_test_user):
        user, _ = create_test_user(email="ent-newest@example.com")
        grant_admin(db, user.id, es.KEY_DAILY_LIMIT, 5)
        grant_admin(db, user.id, es.KEY_DAILY_LIMIT, 2)
        db.commit()
        assert es.effective_limits(db, user.id).daily_limit == 2
        assert len(es.list_entitlements(db, user.id)) == 2


class TestEffectiveLimits:
    def test_defaults_come_from_settings_at_call_time(self, monkeypatch):
        monkeypatch.setattr(settings, "DAILY_SCREENSHOT_LIMIT", 7)
        monkeypatch.setattr(settings, "COOLDOWN_SECONDS", 3)
        limits = es.default_scan_limits()
        assert (limits.daily_limit, limits.cooldown_seconds) == (7, 3)

    def test_daily_limit_override_enforced_in_precheck(self, db, create_test_user):
        user, _ = create_test_user(email="lim-daily@example.com")
        grant_admin(db, user.id, es.KEY_DAILY_LIMIT, 2)
        db.add(ScreenshotUsage(user_id=user.id, screenshots_count=2))
        db.commit()
        with pytest.raises(HTTPException) as exc:
            _check_screenshot_rate_limit(db, user.id, screenshot_count=1)
        assert exc.value.status_code == 429
        assert "Daily limit" in exc.value.detail

    def test_daily_cap_enforced_under_the_lock(self, db, create_test_user, seed_scan_balance):
        user, _ = create_test_user(email="lim-lock@example.com")
        seed_scan_balance(user.id, credits=10)
        grant_admin(db, user.id, es.KEY_DAILY_LIMIT, 1)
        db.add(ScreenshotUsage(user_id=user.id, screenshots_count=1))
        db.commit()
        with pytest.raises(HTTPException) as exc:
            _reserve_scan_credits(db, user.id, count=1)
        assert exc.value.status_code == 429

    def test_cooldown_override_zero_allows_back_to_back(self, db, create_test_user):
        user, _ = create_test_user(email="lim-cooldown@example.com")
        grant_admin(db, user.id, es.KEY_COOLDOWN, 0)
        db.add(ScreenshotUsage(user_id=user.id, screenshots_count=1))
        db.commit()
        _check_screenshot_rate_limit(db, user.id, screenshot_count=1)  # no raise

    def test_free_monthly_override_seeds_balance(self, db, create_test_user):
        user, _ = create_test_user(email="lim-free@example.com")
        grant_admin(db, user.id, es.KEY_FREE_MONTHLY, 10)
        db.commit()
        balance = es.get_or_create_balance(db, user.id)
        assert balance.scan_credits == 10


class TestCatalog:
    def test_products_seeded(self, db):
        ids = {p.id for p in db.query(Product).all()}
        assert {p["id"] for p in es.DEFAULT_PRODUCTS} <= ids

    def test_unlimited_purchase_creates_purchase_sourced_row(self, client, db, auth_headers):
        headers, user = auth_headers(email="cat-unlimited@example.com")
        response = _verify(client, headers, "2000000001", es.UNLIMITED_PRODUCT_ID)
        assert response.status_code == 200, response.text
        assert response.json()["has_unlimited"] is True
        row = db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).one()
        assert row.source == "purchase" and row.purchase_record_id is not None
        assert _balance(db, user.id).has_unlimited is True

    def test_inactive_product_is_400(self, client, db, auth_headers):
        headers, user = auth_headers(email="cat-inactive@example.com")
        product = db.query(Product).filter(Product.id == SCAN_20).one()
        product.active = False
        db.commit()
        response = _verify(client, headers, "2000000002", SCAN_20)
        assert response.status_code == 400

    def test_products_drive_credits_added(self, client, db, auth_headers):
        headers, user = auth_headers(email="cat-credits@example.com")
        product = db.query(Product).filter(Product.id == SCAN_20).one()
        product.credits = 25
        db.commit()
        response = _verify(client, headers, "2000000003", SCAN_20)
        assert response.status_code == 200, response.text
        assert response.json()["credits_added"] == 25


class TestPurchaseInterimCaps:
    def test_non_numeric_transaction_id_422(self, client, auth_headers):
        headers, _ = auth_headers(email="cap-txn@example.com")
        assert _verify(client, headers, "txn-abc", SCAN_20).status_code == 422

    def test_daily_credit_cap_409(self, client, auth_headers):
        headers, _ = auth_headers(email="cap-credits@example.com")
        assert _verify(client, headers, "3000000001", SCAN_50).status_code == 200
        assert _verify(client, headers, "3000000002", SCAN_50).status_code == 200
        response = _verify(client, headers, "3000000003", SCAN_50)
        assert response.status_code == 409

    def test_second_unlimited_409(self, client, auth_headers):
        headers, _ = auth_headers(email="cap-unlimited@example.com")
        assert _verify(client, headers, "3000000011", es.UNLIMITED_PRODUCT_ID).status_code == 200
        assert _verify(client, headers, "3000000012", es.UNLIMITED_PRODUCT_ID).status_code == 409

    def test_verification_count_cap_429(self, client, auth_headers, monkeypatch):
        headers, _ = auth_headers(email="cap-count@example.com")
        monkeypatch.setattr(settings, "PURCHASE_MAX_VERIFICATIONS_PER_DAY", 2)
        assert _verify(client, headers, "3000000021", SCAN_20).status_code == 200
        assert _verify(client, headers, "3000000022", SCAN_20).status_code == 200
        assert _verify(client, headers, "3000000023", SCAN_20).status_code == 429

    def test_revoke_survives_restore_purchases(self, client, db, auth_headers):
        headers, user = auth_headers(email="cap-restore@example.com")
        assert _verify(client, headers, "3000000031", es.UNLIMITED_PRODUCT_ID).status_code == 200
        row = db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).one()
        es.revoke(db, row)
        db.commit()
        assert _balance(db, user.id).has_unlimited is False

        response = client.post("/scan-balance/restore-purchases", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["has_unlimited"] is False
        assert db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).count() == 1


class TestTransactionBoundaries:
    def test_grant_to_user_without_balance_row_stays_in_callers_transaction(
        self, db, create_test_user
    ):
        """Regression: creating the balance row inside grant() must not commit
        the half-done transaction (spec §5 same-transaction rule)."""
        user, _ = create_test_user(email="ent-nobalance@example.com")
        assert db.query(ScanBalance).filter(ScanBalance.user_id == user.id).count() == 0
        grant_admin(db, user.id, es.KEY_UNLIMITED, True)
        db.rollback()
        assert db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).count() == 0
        assert db.query(ScanBalance).filter(ScanBalance.user_id == user.id).count() == 0

    def test_grant_then_commit_persists_row_and_flag(self, db, create_test_user):
        user, _ = create_test_user(email="ent-nobalance2@example.com")
        grant_admin(db, user.id, es.KEY_UNLIMITED, True)
        db.commit()
        assert _balance(db, user.id).has_unlimited is True

    def test_unknown_source_raises(self, db, create_test_user):
        user, _ = create_test_user(email="ent-source@example.com")
        with pytest.raises(ValueError):
            es.grant(db, user_id=user.id, key=es.KEY_UNLIMITED, value=True, source="wizard")


class TestFreeMonthlyAtReset:
    def test_override_applies_when_the_reset_fires(self, client, db, auth_headers, seed_scan_balance):
        headers, user = auth_headers(email="lim-free-reset@example.com")
        seed_scan_balance(
            user.id, credits=0,
            free_scans_reset_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        grant_admin(db, user.id, es.KEY_FREE_MONTHLY, 10)
        db.commit()
        response = client.get("/scan-balance", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["scan_credits"] == 10


class TestOwnerAlert:
    def test_unlimited_purchase_alerts_owner(self, client, auth_headers, monkeypatch):
        from app.api import scan_balance as api

        calls = []
        monkeypatch.setattr(api, "send_owner_alert", lambda subject, body: calls.append(subject) or True)
        headers, _ = auth_headers(email="alert-unlimited@example.com")
        assert _verify(client, headers, "4000000001", es.UNLIMITED_PRODUCT_ID).status_code == 200
        assert len(calls) == 1 and "Unlimited" in calls[0]

    def test_credit_pack_does_not_alert(self, client, auth_headers, monkeypatch):
        from app.api import scan_balance as api

        calls = []
        monkeypatch.setattr(api, "send_owner_alert", lambda subject, body: calls.append(subject) or True)
        headers, _ = auth_headers(email="alert-pack@example.com")
        assert _verify(client, headers, "4000000002", SCAN_20).status_code == 200
        assert calls == []


class TestAdminRoutes:
    """Grant / revoke through the console routes (spec §6.3, §13)."""

    @staticmethod
    def _grant(client, headers, user_id, **body):
        payload = {"key": es.KEY_UNLIMITED, "value": True, "reason": "friend of the owner", **body}
        return client.post(f"/admin/users/{user_id}/entitlements", json=payload, headers=headers)

    def test_grant_unlimited_via_route_sets_flag_and_scanner_passes(
        self, client, db, admin_headers, create_test_user, seed_scan_balance
    ):
        headers, actor = admin_headers(email="ent-route-admin@example.com")
        user, _ = create_test_user(email="ent-route-grant@example.com")
        seed_scan_balance(user.id, credits=0)

        response = self._grant(client, headers, user.id)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["key"] == es.KEY_UNLIMITED and body["value"] is True
        assert body["source"] == "admin_grant" and body["granted_by"] == actor.id
        assert body["user_id"] == user.id and body["active"] is True and body["revoked_at"] is None
        assert _balance(db, user.id).has_unlimited is True
        assert _reserve_scan_credits(db, user.id) is True
        assert _balance(db, user.id).scan_credits == 0

        row = db.query(AdminAuditLog).filter(AdminAuditLog.action == "entitlement.grant",
                                             AdminAuditLog.target_id == user.id).one()
        assert row.actor_user_id == actor.id and row.after["key"] == es.KEY_UNLIMITED
        assert row.target_type == "user" and row.reason == "friend of the owner"

    def test_revoke_via_route_clears_flag_and_scanner_fails(
        self, client, db, admin_headers, create_test_user, seed_scan_balance, step_up_body
    ):
        headers, actor = admin_headers(email="ent-route-admin2@example.com")
        user, _ = create_test_user(email="ent-route-revoke@example.com")
        seed_scan_balance(user.id, credits=0)
        row_id = self._grant(client, headers, user.id).json()["id"]

        url = f"/admin/users/{user.id}/entitlements/{row_id}/revoke"
        response = client.post(url, json=step_up_body(reason="trial over"), headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == row_id and body["revoked_at"] is not None and body["active"] is False
        assert _balance(db, user.id).has_unlimited is False
        assert _reserve_scan_credits(db, user.id) is False  # the 402 path

        assert client.post(url, json=step_up_body(), headers=headers).status_code == 409
        assert client.post(f"/admin/users/{user.id}/entitlements/nope/revoke",
                           json=step_up_body(), headers=headers).status_code == 404
        audit = db.query(AdminAuditLog).filter(AdminAuditLog.action == "entitlement.revoke",
                                               AdminAuditLog.target_id == user.id).one()
        assert audit.before["revoked_at"] is None and audit.after["revoked_at"] is not None

    def test_revoke_of_purchase_sourced_row_survives_restore_purchases(
        self, client, db, admin_headers, auth_headers, step_up_body
    ):
        headers, _ = admin_headers(email="ent-route-admin3@example.com")
        user_headers, user = auth_headers(email="ent-route-purchase@example.com")
        assert _verify(client, user_headers, "3000000041", es.UNLIMITED_PRODUCT_ID).status_code == 200
        row = db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).one()
        assert row.source == "purchase"

        response = client.post(f"/admin/users/{user.id}/entitlements/{row.id}/revoke",
                               json=step_up_body(reason="fabricated receipt"), headers=headers)
        assert response.status_code == 200, response.text
        assert _balance(db, user.id).has_unlimited is False

        restored = client.post("/scan-balance/restore-purchases", headers=user_headers)
        assert restored.status_code == 200 and restored.json()["has_unlimited"] is False
        assert db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).count() == 1

    def test_expired_grant_is_inactive_and_ignored(self, client, db, admin_headers, create_test_user, seed_scan_balance):
        headers, _ = admin_headers(email="ent-route-admin4@example.com")
        user, _ = create_test_user(email="ent-route-expired@example.com")
        seed_scan_balance(user.id, credits=0)
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        response = self._grant(client, headers, user.id, expires_at=past)
        assert response.status_code == 201, response.text
        assert response.json()["active"] is False
        assert _balance(db, user.id).has_unlimited is False
        assert _reserve_scan_credits(db, user.id) is False

    def test_unknown_key_and_wrong_type_are_422(self, client, db, admin_headers, create_test_user):
        headers, _ = admin_headers(email="ent-route-admin5@example.com")
        user, _ = create_test_user(email="ent-route-bad@example.com")
        assert self._grant(client, headers, user.id, key="beta.moon").status_code == 422
        assert self._grant(client, headers, user.id, key=es.KEY_DAILY_LIMIT, value="ten").status_code == 422
        assert self._grant(client, headers, user.id, value=True, reason="").status_code == 422
        assert db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).count() == 0
        assert db.query(AdminAuditLog).filter(AdminAuditLog.target_id == user.id).count() == 0

    def test_entitlement_of_another_user_is_404(self, client, db, admin_headers, create_test_user, step_up_body):
        headers, _ = admin_headers(email="ent-route-admin6@example.com")
        a, _ = create_test_user(email="ent-route-a@example.com")
        b, _ = create_test_user(email="ent-route-b@example.com")
        row_id = self._grant(client, headers, a.id).json()["id"]
        response = client.post(f"/admin/users/{b.id}/entitlements/{row_id}/revoke",
                               json=step_up_body(), headers=headers)
        assert response.status_code == 404
        db.expire_all()
        assert db.query(UserEntitlement).filter(UserEntitlement.id == row_id).one().revoked_at is None
