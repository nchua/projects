"""
GET /coach/debrief and POST /coach/debrief/{id}/adjustments/{adj_id}
(ARISE v3 §15.5) with the SDK and the W1 / W2 services mocked.
"""
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.coach import CoachOutput
from app.services import debrief_service
from app.services.coach_context_service import build_context
from tests.helpers_coach import (
    install_fake_model,
    install_fake_w1,
    install_fake_w2,
    model_output,
    remove_w1,
    seed_four_weeks,
)

CONTRACT_KEYS = {
    "id", "week_start", "summary", "adherence", "highlights", "concerns", "adjustments",
    "next_week_focus", "goal_reports", "generated_at", "source",
}
ADJUSTMENT_KEYS = {"id", "op", "params", "reason", "confidence", "source", "status", "validation_note"}


@pytest.fixture
def api_user(client, db, auth_headers, unique_email, monkeypatch):
    headers, user = auth_headers(email=unique_email("coachapi"))
    seeded = seed_four_weeks(db, user, low_sleep_nights=3)
    applied = install_fake_w1(monkeypatch)
    install_fake_w2(monkeypatch, flags=("ramp_high",), miles_7d=12.5, miles_plan_7d=11.0)
    monkeypatch.setattr(debrief_service, "notify_weekly_report_ready", lambda db, uid: None)
    return headers, seeded, applied


def _get(client, headers, seeded, **params):
    query = {"week_start": seeded.week_start.isoformat(), "client_date": seeded.week_end.isoformat(), **params}
    return client.get("/coach/debrief", params=query, headers=headers)


def _prepare_model(db, seeded, monkeypatch, extra=None):
    ctx = build_context(db, seeded.user.id, seeded.week_start)
    reply = model_output(ctx)
    if extra:
        reply["adjustments"].extend(extra)
    return install_fake_model(monkeypatch, reply)


def test_requires_auth(client):
    assert client.get("/coach/debrief").status_code in (401, 403)


def test_get_debrief_matches_contract(client, db, api_user, monkeypatch):
    headers, seeded, _ = api_user
    calls = _prepare_model(db, seeded, monkeypatch)
    resp = _get(client, headers, seeded)
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert set(body.keys()) == CONTRACT_KEYS
    assert body["week_start"] == seeded.week_start.isoformat()
    assert body["source"] == "model"
    assert body["adherence"] == {"planned": 5, "done": 5, "modified": 0, "moved": 0, "skipped": 0}
    assert {h["kind"] for h in body["highlights"]} >= {"pr", "week_completed_as_planned"}
    assert {c["flag"] for c in body["concerns"]} >= {"ramp_high", "sleep_low"}
    assert body["adjustments"] and set(body["adjustments"][0].keys()) == ADJUSTMENT_KEYS
    assert body["adjustments"][0]["status"] == "proposed"
    assert body["goal_reports"][0]["goal_id"] == seeded.goal.id
    assert body["generated_at"] and body["next_week_focus"]
    assert len(calls) == 1
    # Idempotent: a second GET returns the same row and no second model call.
    again = _get(client, headers, seeded)
    assert again.json()["id"] == body["id"] and len(calls) == 1


def test_invalid_dates_are_422(client, api_user):
    headers, seeded, _ = api_user
    assert client.get("/coach/debrief", params={"week_start": "nope"}, headers=headers).status_code == 422
    assert client.get("/coach/debrief", params={"client_date": "2026-13-40"}, headers=headers).status_code == 422


def test_default_week_start(client, db, api_user, monkeypatch):
    headers, seeded, _ = api_user
    install_fake_model(monkeypatch, "refusal")
    sunday = seeded.week_end
    body = client.get("/coach/debrief", params={"client_date": sunday.isoformat()}, headers=headers).json()
    assert body["week_start"] == seeded.week_start.isoformat()
    wednesday = seeded.week_start + timedelta(days=9)
    body = client.get("/coach/debrief", params={"client_date": wednesday.isoformat()}, headers=headers).json()
    assert body["week_start"] == seeded.week_start.isoformat()


def test_accept_applies_via_w1_and_records_decision(client, db, api_user, monkeypatch):
    headers, seeded, applied = api_user
    _prepare_model(db, seeded, monkeypatch)
    body = _get(client, headers, seeded).json()
    miles = next(a for a in body["adjustments"] if a["op"] == "set_week_miles")

    resp = client.post(
        f"/coach/debrief/{body['id']}/adjustments/{miles['id']}",
        json={"decision": "accept"}, headers=headers,
    )
    assert resp.status_code == 200, resp.json()
    updated = next(a for a in resp.json()["adjustments"] if a["id"] == miles["id"])
    assert updated["status"] == "accepted"
    assert applied == [("set_week_miles", (seeded.next_week, 11.0))]

    row = db.query(CoachOutput).filter(CoachOutput.id == body["id"]).first()
    decision = row.decisions[miles["id"]]
    assert decision["decision"] == "accept" and decision["op"] == "set_week_miles"
    assert decision["affected_planned_hunt_ids"] == ["ph-applied"]
    assert decision["params"]["miles"] == 11.0


def test_dismiss_records_without_applying(client, db, api_user, monkeypatch):
    headers, seeded, applied = api_user
    _prepare_model(db, seeded, monkeypatch)
    body = _get(client, headers, seeded).json()
    adj = body["adjustments"][0]
    resp = client.post(
        f"/coach/debrief/{body['id']}/adjustments/{adj['id']}",
        json={"decision": "dismiss"}, headers=headers,
    )
    assert resp.status_code == 200
    assert next(a for a in resp.json()["adjustments"] if a["id"] == adj["id"])["status"] == "dismissed"
    assert applied == []
    row = db.query(CoachOutput).filter(CoachOutput.id == body["id"]).first()
    assert row.decisions[adj["id"]]["decision"] == "dismiss"
    # Deciding twice is a conflict.
    again = client.post(
        f"/coach/debrief/{body['id']}/adjustments/{adj['id']}",
        json={"decision": "accept"}, headers=headers,
    )
    assert again.status_code == 409


def test_accept_out_of_bounds_is_422(client, db, api_user, monkeypatch):
    headers, seeded, applied = api_user
    _prepare_model(db, seeded, monkeypatch, extra=[
        {"op": "extend_arc", "weeks": 3, "reason": "more base", "confidence": "low", "source": "model"},
    ])
    body = _get(client, headers, seeded).json()
    oob = next(a for a in body["adjustments"] if a["op"] == "extend_arc")
    assert oob["status"] == "out_of_bounds" and oob["validation_note"]
    resp = client.post(
        f"/coach/debrief/{body['id']}/adjustments/{oob['id']}",
        json={"decision": "accept"}, headers=headers,
    )
    assert resp.status_code == 422
    assert applied == []


def test_accept_goal_deadline_uses_goal_service(client, db, api_user, monkeypatch):
    headers, seeded, applied = api_user
    new_deadline = (seeded.goal.deadline + timedelta(weeks=3)).isoformat()
    _prepare_model(db, seeded, monkeypatch, extra=[
        {"op": "set_goal_deadline", "goal_id": seeded.goal.id, "deadline": new_deadline,
         "reason": "behind", "confidence": "high", "source": "model"},
    ])
    body = _get(client, headers, seeded).json()
    adj = next(a for a in body["adjustments"] if a["op"] == "set_goal_deadline")
    resp = client.post(
        f"/coach/debrief/{body['id']}/adjustments/{adj['id']}",
        json={"decision": "accept"}, headers=headers,
    )
    assert resp.status_code == 200, resp.json()
    assert applied == [("set_goal_deadline", (seeded.goal.id, date.fromisoformat(new_deadline)))]
    db.refresh(seeded.goal)
    assert seeded.goal.deadline_extensions == 1


def test_unknown_debrief_or_adjustment_is_404(client, db, api_user, monkeypatch):
    headers, seeded, _ = api_user
    _prepare_model(db, seeded, monkeypatch)
    body = _get(client, headers, seeded).json()
    assert client.post(f"/coach/debrief/{body['id']}/adjustments/nope", json={"decision": "accept"}, headers=headers).status_code == 404
    assert client.post("/coach/debrief/nope/adjustments/nope", json={"decision": "accept"}, headers=headers).status_code == 404
    assert client.post(f"/coach/debrief/{body['id']}/adjustments/nope", json={"decision": "maybe"}, headers=headers).status_code == 422


def test_accept_without_w1_is_503(client, db, api_user, monkeypatch):
    headers, seeded, _ = api_user
    _prepare_model(db, seeded, monkeypatch)
    body = _get(client, headers, seeded).json()
    adj = next(a for a in body["adjustments"] if a["op"] == "set_week_miles")
    remove_w1(monkeypatch)
    resp = client.post(
        f"/coach/debrief/{body['id']}/adjustments/{adj['id']}",
        json={"decision": "accept"}, headers=headers,
    )
    assert resp.status_code == 503
    row = db.query(CoachOutput).filter(CoachOutput.id == body["id"]).first()
    assert row.decisions == {}


def test_applier_value_error_is_422(client, db, api_user, monkeypatch):
    import sys

    headers, seeded, _ = api_user
    _prepare_model(db, seeded, monkeypatch)
    body = _get(client, headers, seeded).json()
    adj = next(a for a in body["adjustments"] if a["op"] == "set_week_miles")

    def boom(db, campaign, *args):
        raise ValueError("Week already logged; cannot re-prescribe.")

    sys.modules["app.services.campaign_service"].apply_set_week_miles = boom
    resp = client.post(
        f"/coach/debrief/{body['id']}/adjustments/{adj['id']}",
        json={"decision": "accept"}, headers=headers,
    )
    assert resp.status_code == 422
    assert "re-prescribe" in resp.json()["detail"]


def test_weekly_report_endpoint_no_longer_pushes(client, api_user, monkeypatch):
    headers, seeded, _ = api_user
    from app.api import weekly_report as weekly_report_api
    from app.services import notification_service

    push = MagicMock()
    monkeypatch.setattr(notification_service, "notify_weekly_report_ready", push)
    assert not hasattr(weekly_report_api, "notify_weekly_report_ready")
    resp = client.get("/progress/weekly-report", params={"week_start": seeded.week_start.isoformat()}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["goal_reports"][0]["goal_id"] == seeded.goal.id
    push.assert_not_called()
