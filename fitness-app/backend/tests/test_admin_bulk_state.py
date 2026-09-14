"""
Bulk soft-delete / restore (console v2 spec §5.4, §6.4, §7.2): ``POST /admin/users/state``
skips rows already in the target state, refuses self and admins per row,
bumps ``token_version`` on restore, and is step-up.
"""
import uuid

import pytest

from app.models.admin import AdminAuditLog
from app.models.user import User
from tests.helpers_admin import assert_no_secret_keys, soft_delete

URL = "/admin/users/state"


@pytest.fixture
def cohort(admin_pair, create_test_user, admin_user):
    headers, actor, target, pwd = admin_pair("state")
    gone, _ = create_test_user(email=f"state-gone-{uuid.uuid4().hex[:8]}@example.com")
    other_admin, _ = admin_user(email=f"state-admin-{uuid.uuid4().hex[:8]}@example.com")
    return headers, actor, pwd, target, gone, other_admin


def _post(client, headers, **body):
    return client.post(URL, headers=headers, json={"reason": "bulk state test", **body})


class TestBulkState:
    def test_delete_groups_and_per_row_protection(self, client, db, cohort):
        headers, actor, pwd, target, gone, other_admin = cohort
        soft_delete(db, gone)
        request_id = f"state-{uuid.uuid4().hex[:8]}"
        response = client.post(
            URL, headers={**headers, "X-Request-ID": request_id},
            json={"user_ids": [target.id, gone.id, actor.id, other_admin.id, "nope"], "action": "delete",
                  "password": pwd, "reason": "cleanup"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert_no_secret_keys(body)
        assert [r["id"] for r in body["applied"]] == [target.id]
        assert body["applied"][0]["is_deleted"] is True and body["applied"][0]["deleted_at"]
        assert body["skipped"] == [{"user_id": gone.id, "why": "already soft-deleted"}]
        assert [f["user_id"] for f in body["failed"]] == [actor.id, other_admin.id, "nope"]
        assert body["failed"][0]["error"] == "Refusing to act on your own account"
        assert body["failed"][1]["error"] == "Refusing to act on another admin"
        assert body["failed"][2]["error"] == "User not found"
        db.expire_all()
        assert db.query(User).filter(User.id == target.id).one().is_deleted is True
        assert db.query(User).filter(User.id == actor.id).one().is_deleted is False
        rows = db.query(AdminAuditLog).filter(AdminAuditLog.request_id == request_id).all()
        assert [(r.action, r.target_id) for r in rows] == [("user.soft_delete", target.id)]
        assert rows[0].reason == "cleanup"

    def test_restore_bumps_token_version_and_skips_live_rows(self, client, db, cohort):
        headers, actor, pwd, target, gone, _ = cohort
        soft_delete(db, gone)
        version = gone.token_version
        response = _post(client, headers, user_ids=[gone.id, target.id], action="restore", password=pwd)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["applied"] == [{"id": gone.id, "is_deleted": False, "deleted_at": None}]
        assert body["skipped"] == [{"user_id": target.id, "why": "not soft-deleted"}]
        db.expire_all()
        assert db.query(User).filter(User.id == gone.id).one().token_version == version + 1
        rows = db.query(AdminAuditLog).filter(AdminAuditLog.target_id == gone.id, AdminAuditLog.action == "user.restore").all()
        assert len(rows) == 1 and rows[0].after["token_version"] == version + 1

    def test_step_up_and_validation(self, client, db, cohort):
        headers, actor, pwd, target, _, _ = cohort
        audits = db.query(AdminAuditLog).count()
        assert _post(client, headers, user_ids=[target.id], action="delete").status_code == 422  # StepUpBody
        assert _post(client, headers, user_ids=[target.id], action="delete", password="wrong").status_code == 401
        assert _post(client, headers, user_ids=[target.id], action="archive", password=pwd).status_code == 422
        assert _post(client, headers, user_ids=[f"u{i}" for i in range(101)], action="delete", password=pwd).status_code == 422
        assert db.query(AdminAuditLog).count() == audits
        db.expire_all()
        assert db.query(User).filter(User.id == target.id).one().is_deleted is False
