"""Credits adjust (control-plane spec §7.1, §16): lock, bounds, idempotency, step-up."""
import uuid

import pytest

from app.models.admin import AdminAuditLog
from app.models.scan_balance import ScanBalance
from tests.helpers_admin import balance_of


def _post(client, headers, user_id, body, key="k1"):
    extra = {"Idempotency-Key": key} if key is not None else {}
    return client.post(f"/admin/users/{user_id}/credits", json=body, headers={**headers, **extra})


def _credits(db, user_id) -> int:
    return balance_of(db, user_id).scan_credits


def _rows(db, key):
    return db.query(AdminAuditLog).filter(AdminAuditLog.idempotency_key == key).all()


@pytest.fixture
def setup(admin_pair, seed_scan_balance):
    headers, actor, target, _ = admin_pair("credits")
    seed_scan_balance(target.id, credits=10)
    return headers, actor, target


class TestAdjust:
    def test_plus_and_minus_with_before_after_and_audit(self, client, db, setup):
        headers, actor, target = setup
        response = _post(client, headers, target.id, {"delta": 5, "reason": "gift"}, key="k-plus")
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["scan_credits_before"], body["scan_credits_after"], body["replayed"]) == (10, 15, False)
        assert _credits(db, target.id) == 15

        row = db.query(AdminAuditLog).filter(AdminAuditLog.id == body["audit_id"]).one()
        assert row.action == "credits.adjust" and row.target_type == "user" and row.target_id == target.id
        assert row.actor_user_id == actor.id and row.reason == "gift"
        assert row.before == {"scan_credits": 10} and row.after == {"scan_credits": 15, "delta": 5}
        assert row.idempotency_key == "k-plus" and len(row.body_sha256) == 64

        response = _post(client, headers, target.id, {"delta": -3, "reason": "refund"}, key="k-minus")
        assert response.status_code == 200
        assert response.json()["scan_credits_after"] == 12 and _credits(db, target.id) == 12

    def test_result_below_zero_is_409_and_unchanged(self, client, db, setup):
        headers, _, target = setup
        response = _post(client, headers, target.id, {"delta": -11, "reason": "too much"}, key="k-neg")
        assert response.status_code == 409, response.text
        assert _credits(db, target.id) == 10
        assert _rows(db, "k-neg") == []

    def test_same_key_same_body_replays_once(self, client, db, setup):
        headers, _, target = setup
        body = {"delta": 4, "reason": "double click"}
        first = _post(client, headers, target.id, body, key="k-dup").json()
        second = _post(client, headers, target.id, body, key="k-dup")
        assert second.status_code == 200, second.text
        assert second.json() == {**first, "replayed": True}
        assert first["replayed"] is False
        assert _credits(db, target.id) == 14  # one change
        assert len(_rows(db, "k-dup")) == 1

    def test_same_key_different_body_is_422(self, client, db, setup):
        headers, _, target = setup
        assert _post(client, headers, target.id, {"delta": 4, "reason": "first body"}, key="k-diff").status_code == 200
        response = _post(client, headers, target.id, {"delta": 4, "reason": "second body"}, key="k-diff")
        assert response.status_code == 422, response.text
        assert _credits(db, target.id) == 14
        assert len(_rows(db, "k-diff")) == 1

    def test_same_key_different_target_is_422(self, client, db, setup, create_test_user):
        headers, _, target = setup
        other, _ = create_test_user(email=f"credits-other-{uuid.uuid4().hex[:8]}@example.com")
        assert _post(client, headers, target.id, {"delta": 1, "reason": "same key"}, key="k-tgt").status_code == 200
        assert _post(client, headers, other.id, {"delta": 1, "reason": "same key"}, key="k-tgt").status_code == 422

    def test_missing_idempotency_key_is_400(self, client, db, setup):
        headers, _, target = setup
        response = _post(client, headers, target.id, {"delta": 1, "reason": "no key"}, key=None)
        assert response.status_code == 400
        assert _credits(db, target.id) == 10

    def test_large_delta_needs_step_up(self, client, db, setup):
        headers, _, target = setup
        assert _post(client, headers, target.id, {"delta": 51, "reason": "big"}, key="k-big-1").status_code == 401
        assert _post(client, headers, target.id, {"delta": 51, "reason": "big", "password": "nope"}, key="k-big-2").status_code == 401
        assert _credits(db, target.id) == 10 and _rows(db, "k-big-1") == [] and _rows(db, "k-big-2") == []

        ok = _post(client, headers, target.id, {"delta": 51, "reason": "big", "password": "TestPass123!"}, key="k-big-3")
        assert ok.status_code == 200, ok.text
        assert _credits(db, target.id) == 61

        # Exactly 50 is not destructive tier; a large negative past zero is 409 even with the password.
        assert _post(client, headers, target.id, {"delta": -50, "reason": "cap"}, key="k-fifty").status_code == 200
        response = _post(client, headers, target.id, {"delta": -60, "reason": "over", "password": "TestPass123!"}, key="k-over")
        assert response.status_code == 409

    def test_zero_delta_and_short_reason_are_422(self, client, setup):
        headers, _, target = setup
        assert _post(client, headers, target.id, {"delta": 0, "reason": "zero"}, key="k-0").status_code == 422
        assert _post(client, headers, target.id, {"delta": 1, "reason": "no"}, key="k-r").status_code == 422
        assert _post(client, headers, target.id, {"delta": 1}, key="k-r2").status_code == 422

    def test_creates_the_balance_row_for_a_user_who_never_scanned(self, client, db, admin_pair):
        headers, _, fresh, _ = admin_pair("credits-fresh")
        assert db.query(ScanBalance).filter(ScanBalance.user_id == fresh.id).first() is None
        response = _post(client, headers, fresh.id, {"delta": 5, "reason": "welcome"}, key="k-fresh")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["scan_credits_after"] - body["scan_credits_before"] == 5
        assert _credits(db, fresh.id) == body["scan_credits_after"]

    def test_unknown_user_404(self, client, setup):
        headers, _, _ = setup
        assert _post(client, headers, "nope", {"delta": 1, "reason": "who"}).status_code == 404
