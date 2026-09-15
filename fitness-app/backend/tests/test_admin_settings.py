"""
Console-editable settings (console v2 spec §4.5, §5.5, §6.4, §6.5, §7.2): the
registry's types and bounds, the resolver order (row → env → code),
``GET /admin/settings`` and ``PATCH /admin/settings/{key}`` (set, reset,
step-up keys, warnings), and one test per moved read site that sets a row
and observes the behaviour.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.api import scan_balance as scan_api
from app.api.screenshot import (
    SpendCeilingExceeded,
    _assert_spend_ceiling,
    _check_screenshot_rate_limit,
)
from app.core.config import settings
from app.core.settings_registry import (
    SETTINGS,
    SETTINGS_REGISTRY,
    TIER_DESTRUCTIVE,
    TYPE_BOOL,
    TYPE_CSV,
    coerce,
)
from app.models.admin import AdminAuditLog
from app.models.app_setting import AppSetting
from app.models.scan_balance import PurchaseRecord
from app.services import purge_service, settings_service
from tests.helpers_admin import assert_no_secret_keys, soft_delete

URL = "/admin/settings"
DESTRUCTIVE = [s for s in SETTINGS if s.tier == TIER_DESTRUCTIVE]


def _patch(client, headers, key, value, **extra):
    return client.patch(f"{URL}/{key}", headers=headers, json={"value": value, "reason": "owner tuning", **extra})


def _row(db, key):
    return db.query(AppSetting).filter(AppSetting.key == key).first()


class TestRegistry:
    EXPECTED_KEYS = {
        "FREE_MONTHLY_SCANS", "DAILY_SCREENSHOT_LIMIT", "COOLDOWN_SECONDS",
        "PURCHASE_MAX_CREDITS_PER_DAY", "PURCHASE_MAX_VERIFICATIONS_PER_DAY",
        "ANTHROPIC_DAILY_CALL_CEILING", "ANTHROPIC_DAILY_CALL_WARN_PERCENT",
        "inactive_after_days", "PURGE_GRACE_DAYS",
        "SCREENSHOT_PROCESSING_ENABLED", "PURGE_SWEEP_ENABLED", "PURCHASE_REQUIRE_JWS",
        "PURCHASE_ALLOWED_ENVIRONMENTS",
    }

    def test_every_spec_key_from_the_spec_is_registered_and_shadows_a_settings_attr(self):
        assert set(SETTINGS_REGISTRY) == self.EXPECTED_KEYS
        for spec in SETTINGS:
            assert spec.label and spec.group in ("scanner", "accounts", "switches")
            if spec.attr is not None:
                assert hasattr(settings, spec.attr), spec.key
            else:
                assert spec.key == "inactive_after_days" and spec.default == 30

    def test_tiers(self):
        assert {s.key for s in DESTRUCTIVE} == {
            "PURGE_GRACE_DAYS", "SCREENSHOT_PROCESSING_ENABLED", "PURGE_SWEEP_ENABLED",
            "PURCHASE_REQUIRE_JWS", "PURCHASE_ALLOWED_ENVIRONMENTS",
        }

    @pytest.mark.parametrize("spec", SETTINGS, ids=[s.key for s in SETTINGS])
    def test_coerce_accepts_the_fallback_and_rejects_the_wrong_type(self, spec):
        assert coerce(spec, spec.fallback()) == spec.fallback()
        wrong = "ten" if spec.type != TYPE_CSV else 5
        with pytest.raises(ValueError):
            coerce(spec, wrong)
        if spec.type == TYPE_BOOL:
            with pytest.raises(ValueError):
                coerce(spec, 1)
        elif spec.type != TYPE_CSV:
            with pytest.raises(ValueError):
                coerce(spec, True)
            if spec.min is not None:
                with pytest.raises(ValueError):
                    coerce(spec, spec.min - 1)
            if spec.max is not None:
                with pytest.raises(ValueError):
                    coerce(spec, spec.max + 1)

    def test_csv_normalises_and_checks_tokens(self):
        spec = SETTINGS_REGISTRY["PURCHASE_ALLOWED_ENVIRONMENTS"]
        assert coerce(spec, " Production , Sandbox ") == "Production,Sandbox"
        with pytest.raises(ValueError):
            coerce(spec, "Production,Moon")
        with pytest.raises(ValueError):
            coerce(spec, " , ")


class TestResolver:
    def test_row_then_env_then_code(self, db, monkeypatch):
        key = "FREE_MONTHLY_SCANS"
        monkeypatch.setattr(settings, key, 7)
        resolved = settings_service.resolve(db, key)
        assert (resolved.value, resolved.default) == (7, 7) and resolved.source in ("env", "code")
        settings_service.set_value(db, key, 12, updated_by="admin-1")
        db.commit()
        resolved = settings_service.resolve(db, key)
        assert (resolved.value, resolved.source, resolved.default) == (12, "console", 7)
        assert settings_service.get(db, key) == 12
        assert settings_service.reset(db, key) is True and settings_service.reset(db, key) is False
        db.commit()
        assert settings_service.get(db, key) == 7

    def test_a_row_the_registry_rejects_falls_through(self, db, client, admin_headers, monkeypatch):
        """A hand-edited or out-of-bounds row must not 500 the scanner or the console (evaluate #5)."""
        monkeypatch.setattr(settings, "FREE_MONTHLY_SCANS", 3)
        db.add(AppSetting(key="FREE_MONTHLY_SCANS", value="ten", updated_at=datetime.now(timezone.utc)))
        db.commit()
        resolved = settings_service.resolve(db, "FREE_MONTHLY_SCANS")
        assert resolved.value == 3 and resolved.source in ("env", "code")
        headers, _ = admin_headers(email=f"settings-{uuid.uuid4().hex[:6]}@example.com")
        rows = {r["key"]: r for r in client.get(URL, headers=headers).json()["items"]}
        assert rows["FREE_MONTHLY_SCANS"]["value"] == 3

    def test_registry_only_key_has_a_code_default(self, db):
        resolved = settings_service.resolve(db, "inactive_after_days")
        assert (resolved.value, resolved.source) == (30, "code")

    def test_unknown_key_raises(self, db):
        with pytest.raises(KeyError):
            settings_service.get(db, "NOT_A_SETTING")

    def test_csv_set(self, db):
        settings_service.set_value(db, "PURCHASE_ALLOWED_ENVIRONMENTS", "Sandbox", updated_by=None)
        db.commit()
        assert settings_service.csv_set(db, "PURCHASE_ALLOWED_ENVIRONMENTS") == {"Sandbox"}


class TestRoutes:
    def test_get_lists_every_registry_key_with_provenance(self, client, db, admin_headers):
        headers, _ = admin_headers(email=f"settings-{uuid.uuid4().hex[:6]}@example.com")
        response = client.get(URL, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {"items", "env"}
        rows = body["items"]
        assert_no_secret_keys(body)
        assert [r["key"] for r in rows] == [s.key for s in SETTINGS]
        by_key = {r["key"]: r for r in rows}
        assert set(rows[0]) == {
            "key", "label", "group", "type", "value", "default", "source", "tier", "warning",
            "updated_at", "updated_by",
        }
        assert by_key["PURGE_GRACE_DAYS"]["tier"] == "destructive"
        assert by_key["FREE_MONTHLY_SCANS"]["value"] == by_key["FREE_MONTHLY_SCANS"]["default"]
        assert by_key["FREE_MONTHLY_SCANS"]["source"] in ("env", "code")
        assert by_key["inactive_after_days"] == {
            **by_key["inactive_after_days"], "value": 30, "default": 30, "source": "code", "warning": None,
        }
        assert by_key["PURCHASE_REQUIRE_JWS"]["warning"].endswith("fail to buy until updated.")
        assert by_key["PURGE_SWEEP_ENABLED"]["warning"].endswith("purged on the next deploy.")
        assert all(by_key[k]["warning"] is None for k in by_key if k not in ("PURCHASE_REQUIRE_JWS", "PURGE_SWEEP_ENABLED"))
        assert response.headers["cache-control"] == "no-store"

    def test_env_block_names_integrations_build_and_admin_without_values(self, client, admin_headers, monkeypatch):
        """§4.5's read-only lines (v2.3): booleans and public names only — a credential never crosses the wire."""
        marker = f"sk-{uuid.uuid4().hex}"
        monkeypatch.setattr(settings, "WHOOP_CLIENT_ID", "whoop-client")
        monkeypatch.setattr(settings, "WHOOP_CLIENT_SECRET", marker)
        monkeypatch.setattr(settings, "WHOOP_REDIRECT_URI", "https://example.com/whoop")
        monkeypatch.setattr(settings, "APNS_KEY_ID", "")
        monkeypatch.setenv("SENDGRID_API_KEY", marker)
        monkeypatch.setenv("SENTRY_DSN", f"https://{marker}@sentry.example.com/1")
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc1234def")
        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
        headers, _ = admin_headers(email=f"settings-{uuid.uuid4().hex[:6]}@example.com")
        response = client.get(URL, headers=headers)
        assert response.status_code == 200, response.text
        env = response.json()["env"]
        assert_no_secret_keys(env)
        assert marker not in response.text and "whoop-client" not in response.text
        assert env["integrations"] == {
            "whoop_configured": True, "apns_configured": False, "apns_topic": settings.APNS_TOPIC,
            "apns_sandbox": bool(settings.APNS_USE_SANDBOX), "sendgrid_configured": True, "sentry_enabled": True,
        }
        assert env["build"]["git_sha"] == "abc1234def" and env["build"]["environment"] == "production"
        assert env["build"]["started_at"].endswith("Z") or "+" in env["build"]["started_at"]
        assert env["admin"] == {
            "bootstrap_email": (settings.ADMIN_BOOTSTRAP_EMAIL or None), "token_ttl_minutes": settings.ADMIN_TOKEN_EXPIRE_MINUTES,
            "lockout_threshold": settings.ADMIN_LOCKOUT_THRESHOLD, "lockout_minutes": settings.ADMIN_LOCKOUT_MINUTES,
            "step_up_failures_to_revoke": settings.ADMIN_STEP_UP_FAILURES_TO_REVOKE,
        }
        monkeypatch.setattr(settings, "WHOOP_CLIENT_SECRET", "")
        monkeypatch.delenv("SENDGRID_API_KEY")
        env = client.get(URL, headers=headers).json()["env"]
        assert env["integrations"]["whoop_configured"] is False and env["integrations"]["sendgrid_configured"] is False

    def test_patch_sets_audits_and_is_live_for_a_fresh_scan_balance(self, client, db, admin_headers, auth_headers):
        """The W4 exit criterion: PATCH then a fresh user's GET /scan-balance sees the new free monthly."""
        headers, actor = admin_headers(email=f"settings-{uuid.uuid4().hex[:6]}@example.com")
        before = settings_service.get(db, "FREE_MONTHLY_SCANS")
        new_value = before + 9
        response = client.patch(
            f"{URL}/FREE_MONTHLY_SCANS", headers={**headers, "X-Request-ID": "set-1"},
            json={"value": new_value, "reason": "launch week promo"},
        )
        assert response.status_code == 200, response.text
        row = response.json()
        assert (row["key"], row["value"], row["default"], row["source"]) == ("FREE_MONTHLY_SCANS", new_value, before, "console")
        assert row["updated_by"] == actor.id and row["updated_at"]
        audit = db.query(AdminAuditLog).filter(AdminAuditLog.request_id == "set-1").one()
        assert audit.action == "settings.update" and audit.target_type == "setting"
        assert audit.target_id == "FREE_MONTHLY_SCANS" and audit.reason == "launch week promo"
        assert audit.before["FREE_MONTHLY_SCANS"] == before and audit.after == {"FREE_MONTHLY_SCANS": new_value, "source": "console"}

        user_headers, _ = auth_headers(email=f"fresh-{uuid.uuid4().hex[:6]}@example.com")
        balance = client.get("/scan-balance", headers=user_headers)
        assert balance.status_code == 200 and balance.json()["scan_credits"] == new_value
        listed = {r["key"]: r for r in client.get(URL, headers=headers).json()["items"]}
        assert listed["FREE_MONTHLY_SCANS"]["value"] == new_value

    def test_reset_deletes_the_row_and_audits_after_null(self, client, db, admin_headers):
        headers, _ = admin_headers(email=f"settings-{uuid.uuid4().hex[:6]}@example.com")
        assert _patch(client, headers, "COOLDOWN_SECONDS", 0).status_code == 200
        assert _row(db, "COOLDOWN_SECONDS") is not None
        response = client.patch(
            f"{URL}/COOLDOWN_SECONDS", headers={**headers, "X-Request-ID": "reset-1"},
            json={"value": None, "reason": "back to default"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["source"] in ("env", "code") and _row(db, "COOLDOWN_SECONDS") is None
        audit = db.query(AdminAuditLog).filter(AdminAuditLog.request_id == "reset-1").one()
        assert audit.before == {"COOLDOWN_SECONDS": 0, "source": "console"} and audit.after is None
        # a second reset has nothing to delete
        assert client.patch(f"{URL}/COOLDOWN_SECONDS", headers=headers, json={"reason": "again"}).status_code == 409

    def test_same_value_is_409_unknown_key_404_bad_value_422(self, client, db, admin_headers):
        headers, _ = admin_headers(email=f"settings-{uuid.uuid4().hex[:6]}@example.com")
        assert _patch(client, headers, "DAILY_SCREENSHOT_LIMIT", 9).status_code == 200
        assert _patch(client, headers, "DAILY_SCREENSHOT_LIMIT", 9).status_code == 409
        assert _patch(client, headers, "NOT_A_SETTING", 1).status_code == 404
        assert _patch(client, headers, "DAILY_SCREENSHOT_LIMIT", "nine").status_code == 422
        assert _patch(client, headers, "DAILY_SCREENSHOT_LIMIT", 0).status_code == 422
        assert _patch(client, headers, "DAILY_SCREENSHOT_LIMIT", True).status_code == 422
        assert _patch(client, headers, "DAILY_SCREENSHOT_LIMIT", 5, reason="no").status_code == 422
        assert db.query(AdminAuditLog).filter(AdminAuditLog.action == "settings.update").count() == 1

    @pytest.mark.parametrize("spec", DESTRUCTIVE, ids=[s.key for s in DESTRUCTIVE])
    def test_destructive_keys_need_the_password(self, client, db, admin_headers, spec):
        headers, actor = admin_headers(email=f"settings-{uuid.uuid4().hex[:6]}@example.com")
        if spec.type == "bool":
            value = not spec.fallback()
        elif spec.type == "csv":
            value = "Sandbox"
        else:
            value = spec.fallback() + 1
        assert _patch(client, headers, spec.key, value).status_code == 401
        assert _patch(client, headers, spec.key, value, password="wrong").status_code == 401
        assert _row(db, spec.key) is None
        db.refresh(actor)
        assert actor.admin_failed_logins == 1
        ok = _patch(client, headers, spec.key, value, password="TestPass123!")
        assert ok.status_code == 200, ok.text
        assert ok.json()["value"] == value and ok.json()["source"] == "console"

    def test_warning_counts_are_live(self, client, db, admin_headers, create_test_user):
        headers, _ = admin_headers(email=f"settings-{uuid.uuid4().hex[:6]}@example.com")
        base = {r["key"]: r["warning"] for r in client.get(URL, headers=headers).json()["items"]}
        unsigned_before = int(base["PURCHASE_REQUIRE_JWS"].split()[0])
        eligible_before = int(base["PURGE_SWEEP_ENABLED"].split()[0])

        buyer, _ = create_test_user(email=f"unsigned-{uuid.uuid4().hex[:6]}@example.com")
        db.add(PurchaseRecord(user_id=buyer.id, product_id="com.nickchua.fitnessapp.scan_20",
                              transaction_id=str(7_000_000_000 + int(uuid.uuid4().hex[:6], 16)),
                              credits_added=20, purchase_type="consumable", verified=False))
        db.add(PurchaseRecord(user_id=buyer.id, product_id="com.nickchua.fitnessapp.scan_20",
                              transaction_id=str(7_100_000_000 + int(uuid.uuid4().hex[:6], 16)),
                              credits_added=20, purchase_type="consumable", verified=True, environment="Sandbox"))
        db.add(PurchaseRecord(user_id=buyer.id, product_id="com.nickchua.fitnessapp.scan_20",
                              transaction_id=str(7_200_000_000 + int(uuid.uuid4().hex[:6], 16)),
                              credits_added=20, purchase_type="consumable", verified=False,
                              created_at=datetime.now(timezone.utc) - timedelta(days=40)))
        gone, _ = create_test_user(email=f"eligible-{uuid.uuid4().hex[:6]}@example.com")
        soft_delete(db, gone, days_ago=40)
        db.commit()

        now = {r["key"]: r["warning"] for r in client.get(URL, headers=headers).json()["items"]}
        assert int(now["PURCHASE_REQUIRE_JWS"].split()[0]) == unsigned_before + 1
        assert int(now["PURGE_SWEEP_ENABLED"].split()[0]) == eligible_before + 1


class TestMovedReadSites:
    """Each read site that left ``settings.X``: set a row, observe the behaviour (§6.5, §7.2)."""

    def _set(self, db, key, value):
        settings_service.set_value(db, key, value, updated_by=None)
        db.commit()

    def test_grace_days(self, client, db, admin_pair, step_up_body):
        headers, _, target, _ = admin_pair("grace")
        soft_delete(db, target, days_ago=6)
        body = step_up_body(reason="past a five-day grace", confirm_email=target.email)
        assert client.post(f"/admin/users/{target.id}/purge", json=body, headers=headers).status_code == 409
        self._set(db, "PURGE_GRACE_DAYS", 5)
        assert purge_service.grace_days(db) == 5
        assert purge_service.is_purge_eligible(db, target) is True
        detail = client.get(f"/admin/users/{target.id}", headers=headers).json()
        assert detail["account"]["status"] == "purge_eligible"
        assert client.post(f"/admin/users/{target.id}/purge", json=body, headers=headers).status_code == 200

    def test_sweep_gate(self, db, monkeypatch):
        monkeypatch.setattr(settings, "PURGE_SWEEP_ENABLED", False)
        assert purge_service.sweep_enabled(db) is False
        self._set(db, "PURGE_SWEEP_ENABLED", True)
        assert purge_service.sweep_enabled(db) is True

    def test_screenshot_kill_switch(self, db, create_test_user, monkeypatch):
        monkeypatch.setattr(settings, "SCREENSHOT_PROCESSING_ENABLED", True)
        user, _ = create_test_user(email=f"switch-{uuid.uuid4().hex[:6]}@example.com")
        _check_screenshot_rate_limit(db, user.id, screenshot_count=1)  # on: passes
        self._set(db, "SCREENSHOT_PROCESSING_ENABLED", False)
        with pytest.raises(HTTPException) as exc:
            _check_screenshot_rate_limit(db, user.id, screenshot_count=1)
        assert exc.value.status_code == 503

    def test_anthropic_ceiling(self, db, monkeypatch):
        monkeypatch.setattr(settings, "ANTHROPIC_DAILY_CALL_CEILING", 500)
        _assert_spend_ceiling(db, 1, None)
        self._set(db, "ANTHROPIC_DAILY_CALL_CEILING", 0)
        with pytest.raises(SpendCeilingExceeded):
            _assert_spend_ceiling(db, 1, None)

    def test_jws_required_and_environments(self, client, db, auth_headers, monkeypatch):
        monkeypatch.setattr(settings, "PURCHASE_REQUIRE_JWS", False)
        headers, _ = auth_headers(email=f"jws-{uuid.uuid4().hex[:6]}@example.com")
        payload = {"transaction_id": str(8_000_000_000 + int(uuid.uuid4().hex[:6], 16)),
                   "product_id": "com.nickchua.fitnessapp.scan_20"}
        self._set(db, "PURCHASE_REQUIRE_JWS", True)
        response = client.post("/scan-balance/verify-purchase", headers=headers, json=payload)
        assert response.status_code == 422 and response.json()["detail"] == "signed_transaction required"
        self._set(db, "PURCHASE_ALLOWED_ENVIRONMENTS", "Production")
        assert scan_api._allowed_environments(db) == {"Production"}

    def test_purchase_caps(self, client, db, auth_headers, monkeypatch):
        monkeypatch.setattr(settings, "PURCHASE_MAX_VERIFICATIONS_PER_DAY", 5)
        headers, _ = auth_headers(email=f"caps-{uuid.uuid4().hex[:6]}@example.com")
        self._set(db, "PURCHASE_MAX_VERIFICATIONS_PER_DAY", 1)
        base = 8_500_000_000 + int(uuid.uuid4().hex[:5], 16) * 10
        first = client.post("/scan-balance/verify-purchase", headers=headers,
                            json={"transaction_id": str(base), "product_id": "com.nickchua.fitnessapp.scan_20"})
        assert first.status_code == 200, first.text
        second = client.post("/scan-balance/verify-purchase", headers=headers,
                             json={"transaction_id": str(base + 1), "product_id": "com.nickchua.fitnessapp.scan_20"})
        assert second.status_code == 429

    def test_scanner_defaults_and_inactive_after_days(self, client, db, admin_headers, create_test_user):
        from app.services import entitlement_service as es

        self._set(db, "DAILY_SCREENSHOT_LIMIT", 3)
        self._set(db, "COOLDOWN_SECONDS", 1)
        limits = es.default_scan_limits(db)
        assert (limits.daily_limit, limits.cooldown_seconds) == (3, 1)

        headers, _ = admin_headers(email=f"inactive-{uuid.uuid4().hex[:6]}@example.com")
        user, _ = create_test_user(email=f"idle-{uuid.uuid4().hex[:6]}@example.com")
        user.last_login_at = datetime.now(timezone.utc) - timedelta(days=10)
        db.commit()
        assert client.get(f"/admin/users/{user.id}", headers=headers).json()["account"]["status"] == "active"
        self._set(db, "inactive_after_days", 7)
        assert client.get(f"/admin/users/{user.id}", headers=headers).json()["account"]["status"] == "inactive"
        rows = client.get("/admin/users", headers=headers, params={"q": user.email, "status": "inactive"}).json()
        assert [r["id"] for r in rows["items"]] == [user.id]
