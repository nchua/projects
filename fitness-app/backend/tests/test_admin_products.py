"""Product catalog upsert (control-plane spec §6.4, §13): create, edit, immutable id, deactivate."""
import uuid

import pytest

from app.models.admin import AdminAuditLog
from app.models.entitlement import Product
from app.services import entitlement_service as es
from tests.helpers_admin import product_body


def _body(product_id: str, **overrides):
    return product_body(product_id, reason="catalog change", **overrides)


@pytest.fixture
def admin(admin_headers):
    return admin_headers(email=f"products-admin-{uuid.uuid4().hex[:8]}@example.com")


class TestProductsUpsert:
    def test_create_then_list_and_audit(self, client, db, admin):
        headers, actor = admin
        product_id = f"com.test.{uuid.uuid4().hex[:8]}"
        response = client.post("/admin/products", json=_body(product_id), headers=headers)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["id"] == product_id and body["credits"] == 5 and body["active"] is True
        assert set(body) == {"id", "kind", "credits", "entitlement_key", "display_name", "active", "sort_order", "created_at", "updated_at"}
        assert product_id in {p["id"] for p in client.get("/admin/products", headers=headers).json()}

        row = db.query(AdminAuditLog).filter(AdminAuditLog.action == "product.upsert",
                                             AdminAuditLog.target_id == product_id).one()
        assert row.target_type == "product" and row.actor_user_id == actor.id
        assert row.before is None and row.after["credits"] == 5 and row.reason == "catalog change"

    def test_create_existing_id_is_409(self, client, db, admin):
        headers, _ = admin
        response = client.post("/admin/products", json=_body(es.UNLIMITED_PRODUCT_ID), headers=headers)
        assert response.status_code == 409
        assert db.query(AdminAuditLog).filter(AdminAuditLog.target_id == es.UNLIMITED_PRODUCT_ID).count() == 0

    def test_patch_edits_and_id_is_immutable(self, client, db, admin):
        headers, _ = admin
        product_id = f"com.test.{uuid.uuid4().hex[:8]}"
        assert client.post("/admin/products", json=_body(product_id), headers=headers).status_code == 201

        response = client.patch(f"/admin/products/{product_id}",
                                json=_body(product_id, credits=25, display_name="Bigger pack"), headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["credits"] == 25 and response.json()["display_name"] == "Bigger pack"
        row = db.query(AdminAuditLog).filter(AdminAuditLog.action == "product.upsert",
                                             AdminAuditLog.target_id == product_id).order_by(AdminAuditLog.created_at.desc()).first()
        assert row.before["credits"] == 5 and row.after["credits"] == 25

        assert client.patch(f"/admin/products/{product_id}", json=_body("com.other.id"), headers=headers).status_code == 422
        assert client.patch("/admin/products/com.missing", json=_body("com.missing"), headers=headers).status_code == 404
        db.expire_all()
        assert db.query(Product).filter(Product.id == product_id).one().id == product_id

    def test_entitlement_key_must_be_registered(self, client, admin):
        headers, _ = admin
        product_id = f"com.test.{uuid.uuid4().hex[:8]}"
        bad = client.post("/admin/products", json=_body(product_id, kind="non_consumable", entitlement_key="beta.moon"), headers=headers)
        assert bad.status_code == 422
        good = client.post("/admin/products", json=_body(product_id, kind="non_consumable", entitlement_key=es.KEY_UNLIMITED), headers=headers)
        assert good.status_code == 201, good.text
        assert client.post("/admin/products", json=_body("x", kind="magic"), headers=headers).status_code == 422

    def test_deactivate_is_step_up_and_blocks_purchases(self, client, db, admin, auth_headers):
        headers, _ = admin
        product_id = f"com.test.{uuid.uuid4().hex[:8]}"
        assert client.post("/admin/products", json=_body(product_id), headers=headers).status_code == 201

        url = f"/admin/products/{product_id}"
        assert client.patch(url, json=_body(product_id, active=False), headers=headers).status_code == 401
        assert client.patch(url, json=_body(product_id, active=False, password="wrong"), headers=headers).status_code == 401
        db.expire_all()
        assert db.query(Product).filter(Product.id == product_id).one().active is True

        ok = client.patch(url, json=_body(product_id, active=False, password="TestPass123!"), headers=headers)
        assert ok.status_code == 200, ok.text
        assert ok.json()["active"] is False

        user_headers, _ = auth_headers(email=f"products-buyer-{uuid.uuid4().hex[:8]}@example.com")
        purchase = client.post("/scan-balance/verify-purchase", headers=user_headers,
                               json={"transaction_id": "3000000099", "product_id": product_id})
        assert purchase.status_code == 400
