"""Exercise-family backfill (control-plane spec §7.3, §16): dry run by default, audited apply."""

import pytest

from app.models.admin import AdminAuditLog
from app.models.exercise import Exercise
from app.services.exercise_family_defs import family_for_name

URL = "/admin/maintenance/exercise-families"


@pytest.fixture
def setup(db, admin_pair):
    headers, actor, user, _ = admin_pair("families")
    assert family_for_name("Bench Press") == "bench_press"
    resolvable = Exercise(name="Bench Press", category="compound", is_custom=True, user_id=user.id)
    orphan = Exercise(name="Zercher Yoke Carry", category="compound", is_custom=True, user_id=user.id)
    db.add_all([resolvable, orphan])
    db.commit()
    return headers, actor, user, resolvable, orphan


def _audits(db):
    return db.query(AdminAuditLog).filter(AdminAuditLog.action == "maintenance.family_backfill").all()


class TestFamilyBackfill:
    def test_dry_run_reports_unresolved_and_writes_nothing(self, client, db, setup):
        headers, _, user, resolvable, orphan = setup
        response = client.post(URL, json={"reason": "weekly check"}, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["dry_run"] is True and body["families_changed"] == 0
        assert body["exercises_updated"] == 1 and body["total"] == 2 and body["assigned"] == 1
        assert body["unresolved"] == [{"name": "Zercher Yoke Carry", "is_custom": True, "user_id": user.id}]
        db.expire_all()
        assert resolvable.family_id is None and orphan.family_id is None
        assert _audits(db) == []

    def test_apply_updates_and_a_second_apply_is_zero(self, client, db, setup, step_up_body):
        headers, actor, user, resolvable, orphan = setup
        response = client.post(URL, json=step_up_body(reason="apply", dry_run=False), headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["dry_run"] is False and body["exercises_updated"] == 1 and body["assigned"] == 1
        assert [u["name"] for u in body["unresolved"]] == ["Zercher Yoke Carry"]
        db.expire_all()
        assert resolvable.family_id == "bench_press" and orphan.family_id is None
        (row,) = _audits(db)
        assert row.actor_user_id == actor.id and row.target_type == "system" and row.reason == "apply"
        assert row.after["exercises_updated"] == 1 and row.after["unresolved"] == 1

        again = client.post(URL, json=step_up_body(reason="apply again", dry_run=False), headers=headers)
        assert again.status_code == 200
        assert again.json()["exercises_updated"] == 0 and again.json()["assigned"] == 1
        assert len(_audits(db)) == 2

    def test_apply_needs_step_up(self, client, db, setup):
        headers, _, _, resolvable, _ = setup
        assert client.post(URL, json={"reason": "apply", "dry_run": False}, headers=headers).status_code == 401
        assert client.post(URL, json={"reason": "apply", "dry_run": False, "password": "wrong"},
                           headers=headers).status_code == 401
        db.expire_all()
        assert resolvable.family_id is None and _audits(db) == []
