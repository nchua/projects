"""
Campaign import for a target user (control-plane spec §7.2, §16): template
vs pasted phases, the XOR rule, dry run, 409 / replace, objectives, audit.
"""
from datetime import timedelta

import pytest

from app.models.admin import AdminAuditLog
from app.models.campaign import Campaign, CampaignStatus, PlannedHunt, PlannedHuntStatus
from app.models.goal import Goal
from app.services import campaign_service
from app.services.campaign_service import materialize_range
from tests.helpers_w1 import MONDAY, import_plan, load_phases

ARC_NAMES = ["Months 1–2", "Months 3–4", "Months 5–6"]


def _body(**overrides):
    body = {"name": "Run Base + Strength", "template": "owner_hybrid", "reason": "friend onboarding",
            "client_date": MONDAY.isoformat()}
    body.update(overrides)
    return body


@pytest.fixture
def setup(admin_pair):
    headers, actor, target, _ = admin_pair("import")
    return headers, actor, target


def _import(client, headers, user_id, **overrides):
    return client.post(f"/admin/users/{user_id}/campaign/import", json=_body(**overrides), headers=headers)


class TestImport:
    def test_template_reproduces_the_script_result(self, client, db, setup):
        headers, actor, target = setup
        response = _import(client, headers, target.id)
        assert response.status_code == 201, response.text
        body = response.json()
        assert [a["name"] for a in body["arcs"]] == ARC_NAMES
        assert sum(len(a["templates"]) for a in body["arcs"]) == 21
        assert body["templates_created"] == 21 and body["warnings"] == []
        assert body["status"] == "active" and body["source"] == "import" and body["dry_run"] is False
        assert body["retired_campaign_id"] is None and body["planned_hunts_deleted"] == 0
        assert body["arcs_preview"] is None and body["objectives_created"] == 0
        assert campaign_service.get_active_campaign(db, target.id).id == body["id"]

        row = db.query(AdminAuditLog).filter(AdminAuditLog.action == "campaign.import").one()
        assert row.target_type == "user" and row.target_id == target.id and row.actor_user_id == actor.id
        assert row.before == {"active_campaign_id": None, "status": None}
        assert row.after["campaign_id"] == body["id"] and row.after["arcs"] == 3
        assert row.after["templates_created"] == 21 and row.after["payload"]["template"] == "owner_hybrid"
        assert "password" not in row.after["payload"]

    def test_pasted_phases_match_the_template(self, client, db, setup):
        headers, _, target = setup
        response = _import(client, headers, target.id, template=None, phases=load_phases())
        assert response.status_code == 201, response.text
        assert sum(len(a["templates"]) for a in response.json()["arcs"]) == 21
        assert response.json()["warnings"] == []

    def test_both_or_neither_is_422(self, client, db, setup):
        headers, _, target = setup
        assert _import(client, headers, target.id, phases=load_phases()).status_code == 422
        assert _import(client, headers, target.id, template=None).status_code == 422
        assert _import(client, headers, target.id, template="not_a_template").status_code == 422
        assert db.query(Campaign).filter(Campaign.user_id == target.id).count() == 0

    def test_dry_run_previews_and_writes_nothing(self, client, db, setup):
        headers, _, target = setup
        campaigns, audits = db.query(Campaign).count(), db.query(AdminAuditLog).count()
        response = _import(client, headers, target.id, dry_run=True)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["dry_run"] is True and body["id"] is None and body["arcs"] == []
        assert [a["name"] for a in body["arcs_preview"]] == ARC_NAMES
        assert [a["templates"] for a in body["arcs_preview"]] == [7, 7, 7]
        assert body["arcs_preview"][0]["run_miles_min"] == 7 and body["arcs_preview"][0]["weeks"] == 8
        assert body["warnings"] == [] and body["templates_created"] == 0
        assert db.query(Campaign).count() == campaigns and db.query(AdminAuditLog).count() == audits

    def test_409_without_replace_and_replace_retires_and_counts_hunts(self, client, db, setup):
        headers, _, target = setup
        old, _ = import_plan(db, target.id, start=MONDAY)
        materialize_range(db, target.id, MONDAY, MONDAY + timedelta(days=13), today=MONDAY)
        db.commit()
        future = (
            db.query(PlannedHunt)
            .filter(PlannedHunt.campaign_id == old.id, PlannedHunt.status == PlannedHuntStatus.PLANNED.value,
                    PlannedHunt.session_id.is_(None))
            .count()
        )
        assert future > 0

        assert _import(client, headers, target.id).status_code == 409
        assert _import(client, headers, target.id, replace=True).status_code == 401  # step-up
        assert _import(client, headers, target.id, replace=True, password="wrong").status_code == 401
        assert db.query(AdminAuditLog).filter(AdminAuditLog.action == "campaign.import").count() == 0

        response = _import(client, headers, target.id, replace=True, password="TestPass123!")
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["retired_campaign_id"] == old.id and body["planned_hunts_deleted"] == future
        db.expire_all()
        assert db.query(Campaign).filter(Campaign.id == old.id).one().status == CampaignStatus.COMPLETED.value
        assert db.query(PlannedHunt).filter(PlannedHunt.campaign_id == old.id,
                                            PlannedHunt.status == PlannedHuntStatus.PLANNED.value).count() == 0
        assert campaign_service.get_active_campaign(db, target.id).id == body["id"]
        row = db.query(AdminAuditLog).filter(AdminAuditLog.action == "campaign.import").one()
        assert row.before == {"active_campaign_id": old.id, "status": "active"}
        assert row.after["retired_campaign_id"] == old.id and row.after["planned_hunts_deleted"] == future

    def test_dry_run_with_replace_needs_no_password(self, client, db, setup):
        headers, _, target = setup
        old, _ = import_plan(db, target.id, start=MONDAY)
        response = _import(client, headers, target.id, dry_run=True, replace=True)
        assert response.status_code == 200, response.text
        assert response.json()["retired_campaign_id"] == old.id
        db.expire_all()
        assert db.query(Campaign).filter(Campaign.id == old.id).one().status == "active"

    def test_objectives_are_created_under_the_campaign(self, client, db, setup):
        headers, _, target = setup
        objective = {"kind": "run", "target_miles": 5, "run_scope": "long_run", "by": "arc_end"}
        response = _import(client, headers, target.id, objectives=[objective])
        assert response.status_code == 201, response.text
        assert response.json()["objectives_created"] == 1
        goal = db.query(Goal).filter(Goal.user_id == target.id).one()
        assert goal.campaign_id == response.json()["id"] and goal.kind == "run"

    def test_unknown_user_404(self, client, setup):
        headers, _, _ = setup
        assert _import(client, headers, "nope").status_code == 404
