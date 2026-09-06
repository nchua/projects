"""
The break-glass owner scripts must go through the same services the console
uses (control-plane spec pillar 4) so they cannot drift from the routes.
"""
import pytest

from app.models.admin import AdminAuditLog
from app.models.entitlement import UserEntitlement
from app.models.scan_balance import ScanBalance
from app.services import entitlement_service as es
from tests.helpers_admin import load_script


class TestGrantOwnerUnlimitedScans:
    def test_grants_through_the_entitlement_service_and_audits(self, db, client, create_test_user, auth_headers):
        module = load_script("grant_owner_unlimited_scans")
        assert module.entitlement_service.grant is es.grant  # shared symbol, no drift

        headers, user = auth_headers(email="script-owner@example.com")
        result = module.grant_owner_unlimited(db, user.email)
        assert result["changed"] is True and result["has_unlimited"] is True

        rows = db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).all()
        assert [r.source for r in rows] == ["admin_grant"]
        audit_row = (
            db.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "entitlement.grant", AdminAuditLog.target_id == user.id)
            .one()
        )
        assert audit_row.actor_user_id is None and audit_row.reason == module.REASON

        # Idempotent.
        again = module.grant_owner_unlimited(db, user.email)
        assert again["changed"] is False and again["has_unlimited"] is True
        assert db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).count() == 1

        # The grant survives the sync that "Restore Purchases" triggers.
        response = client.post("/scan-balance/restore-purchases", headers=headers)
        assert response.status_code == 200 and response.json()["has_unlimited"] is True
        db.expire_all()
        assert db.query(ScanBalance).filter(ScanBalance.user_id == user.id).one().has_unlimited is True

    def test_unknown_email_raises(self, db):
        module = load_script("grant_owner_unlimited_scans")
        with pytest.raises(LookupError):
            module.grant_owner_unlimited(db, "nobody-script@example.com")


class TestScriptsShareServiceSymbols:
    """The console routes and the fallback scripts call the same functions (spec §16)."""

    def test_backfill_script_and_route_share_the_family_functions(self):
        from app.services import admin_service, exercise_family_service

        module = load_script("backfill_exercise_families")
        assert module.ensure_families is exercise_family_service.ensure_families
        assert module.assign_family_ids is exercise_family_service.assign_family_ids
        # The route runs the two halves ``assign_family_ids`` is built from.
        assert admin_service.ensure_families is exercise_family_service.ensure_families
        assert admin_service.planned_family_updates is exercise_family_service.planned_family_updates
        assert admin_service.apply_family_updates is exercise_family_service.apply_family_updates

    def test_import_script_uses_the_console_parser_and_the_committed_template_matches(self):
        from app.services import campaign_templates

        module = load_script("import_training_calendar")
        assert module.load_phases_js is campaign_templates.load_phases_js
        assert campaign_templates.load_template("owner_hybrid") == module.load_phases()

    def test_grant_script_uses_the_entitlement_service_and_audit(self):
        from app.services import audit_service

        module = load_script("grant_owner_unlimited_scans")
        assert module.entitlement_service is es
        assert module.audit is audit_service.audit
