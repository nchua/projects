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
