"""
Integration tests for the Sync API (iOS offline-queue bulk sync).

Endpoints tested:
- POST /sync - Bulk sync of offline workouts + bodyweight entries
- GET /sync/status - Last sync timestamp + pending counts

Ported from the manual script fitness-app/test-sync.js into pytest.

Behavior notes (app/api/sync.py):
- Workout conflicts are matched on (user, date): the existing session is
  soft-deleted and the client copy wins; a SyncConflict with resolution
  "client_wins" is reported.
- Bodyweight conflicts on the same date update the existing row in place
  (status "updated") and are NOT reported in the conflicts list.
- kg bodyweight entries are converted to lb (weight * 2.20462) for storage.
- Synced workouts are stamped with synced_at, so they never count as
  pending in /sync/status.
"""
from datetime import date, datetime, timezone

import pytest

from app.models.exercise import Exercise

KG_TO_LB = 2.20462


def _seed_exercise(
    db,
    *,
    id: str = "ex-sync-bench",
    name: str = "Barbell Bench Press",
    category: str = "compound",
) -> Exercise:
    """Insert an exercise row into the test DB and return it."""
    exercise = Exercise(id=id, name=name, category=category)
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise


def _workout_payload(exercise_id: str, *, day: date = None, notes: str = "Synced workout", sets: list = None) -> dict:
    return {
        "date": (day or date.today()).isoformat(),
        "notes": notes,
        "exercises": [
            {
                "exercise_id": exercise_id,
                "order_index": 0,
                "sets": sets
                or [
                    {"weight": 135, "reps": 10, "set_number": 1},
                    {"weight": 155, "reps": 8, "set_number": 2},
                ],
            }
        ],
    }


def _sync_payload(*, workouts: list = None, bodyweight_entries: list = None, profile: dict = None) -> dict:
    payload = {
        "workouts": workouts or [],
        "bodyweight_entries": bodyweight_entries or [],
        "client_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if profile is not None:
        payload["profile"] = profile
    return payload


class TestBulkSync:
    """POST /sync."""

    def test_bulk_payload_creates_workout_and_bodyweight(self, client, db, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("sync"))
        exercise = _seed_exercise(db)
        today = date.today()

        resp = client.post(
            "/sync",
            json=_sync_payload(
                workouts=[_workout_payload(exercise.id)],
                bodyweight_entries=[{"date": today.isoformat(), "weight": 175, "weight_unit": "lb"}],
            ),
            headers=headers,
        )

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        # Response contract.
        assert body["success"] is True
        assert body["synced_at"]
        assert body["workouts_synced"] == 1
        assert body["bodyweight_entries_synced"] == 1
        assert body["profile_synced"] is False
        assert body["conflicts"] == []
        statuses = {(r["entity_type"], r["status"]) for r in body["results"]}
        assert ("workout", "created") in statuses
        assert ("bodyweight", "created") in statuses
        assert all(r["entity_id"] != "unknown" for r in body["results"])

        # Records actually exist.
        workouts = client.get("/workouts", headers=headers).json()
        assert len(workouts) == 1
        assert workouts[0]["notes"] == "Synced workout"
        assert workouts[0]["total_sets"] == 2

        bodyweight = client.get("/bodyweight", headers=headers).json()
        assert bodyweight["total_entries"] == 1
        assert bodyweight["entries"][0]["weight_lb"] == 175.0

    def test_same_date_workout_conflict_client_wins(self, client, db, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("sync"))
        exercise = _seed_exercise(db)

        first = client.post(
            "/sync",
            json=_sync_payload(workouts=[_workout_payload(exercise.id, notes="Original")]),
            headers=headers,
        )
        assert first.status_code == 200, first.json()
        assert first.json()["conflicts"] == []

        resp = client.post(
            "/sync",
            json=_sync_payload(
                workouts=[
                    _workout_payload(
                        exercise.id,
                        notes="Updated",
                        sets=[{"weight": 185, "reps": 5, "set_number": 1}],
                    )
                ]
            ),
            headers=headers,
        )

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["workouts_synced"] == 1
        assert len(body["conflicts"]) == 1
        conflict = body["conflicts"][0]
        assert conflict["entity_type"] == "workout"
        assert conflict["resolution"] == "client_wins"
        assert "Replaced workout" in conflict["details"]

        # The original session was soft-deleted; only the client copy survives.
        workouts = client.get("/workouts", headers=headers).json()
        assert len(workouts) == 1
        assert workouts[0]["notes"] == "Updated"
        assert workouts[0]["total_sets"] == 1

    def test_same_date_bodyweight_updates_in_place(self, client, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("sync"))
        today = date.today()

        first = client.post(
            "/sync",
            json=_sync_payload(
                bodyweight_entries=[{"date": today.isoformat(), "weight": 175, "weight_unit": "lb"}]
            ),
            headers=headers,
        )
        assert first.status_code == 200, first.json()

        resp = client.post(
            "/sync",
            json=_sync_payload(
                bodyweight_entries=[{"date": today.isoformat(), "weight": 172, "weight_unit": "lb"}]
            ),
            headers=headers,
        )

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["bodyweight_entries_synced"] == 1
        statuses = {(r["entity_type"], r["status"]) for r in body["results"]}
        assert ("bodyweight", "updated") in statuses
        # Bodyweight same-date resolution is silent — not reported as a conflict.
        assert body["conflicts"] == []

        # No duplicate row; the value was updated in place.
        bodyweight = client.get("/bodyweight", headers=headers).json()
        assert bodyweight["total_entries"] == 1
        assert bodyweight["entries"][0]["weight_lb"] == 172.0

    def test_kg_bodyweight_converted_to_lb(self, client, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("sync"))

        resp = client.post(
            "/sync",
            json=_sync_payload(
                bodyweight_entries=[{"date": date.today().isoformat(), "weight": 80, "weight_unit": "kg"}]
            ),
            headers=headers,
        )

        assert resp.status_code == 200, resp.json()
        assert resp.json()["bodyweight_entries_synced"] == 1

        # 80 kg * 2.20462 = 176.37 lb stored.
        bodyweight = client.get("/bodyweight", headers=headers).json()
        assert bodyweight["entries"][0]["weight_lb"] == pytest.approx(80 * KG_TO_LB, abs=0.01)


class TestSyncStatus:
    """GET /sync/status."""

    def test_fresh_user_status_shape(self, client, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("sync"))

        resp = client.get("/sync/status", headers=headers)

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["last_sync_at"] is None
        assert body["pending_workouts"] == 0
        assert body["pending_bodyweight_entries"] == 0
        assert body["is_synced"] is True

    def test_status_after_sync_reports_last_sync(self, client, db, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("sync"))
        exercise = _seed_exercise(db)

        sync = client.post(
            "/sync",
            json=_sync_payload(workouts=[_workout_payload(exercise.id)]),
            headers=headers,
        )
        assert sync.status_code == 200, sync.json()

        resp = client.get("/sync/status", headers=headers)

        assert resp.status_code == 200
        body = resp.json()
        # The synced workout is stamped with synced_at, so nothing is pending.
        assert body["last_sync_at"] is not None
        assert body["pending_workouts"] == 0
        assert body["is_synced"] is True


class TestSyncAuth:
    """Authentication requirements on /sync."""

    def test_post_missing_token_rejected(self, client):
        # FastAPI's default HTTPBearer returns 403 when the Authorization
        # header is missing entirely (not 401) — same convention pinned in
        # test_auth_hardening.py. Unauthenticated callers cannot reach it.
        resp = client.post("/sync", json=_sync_payload())
        assert resp.status_code == 403

    def test_status_missing_token_rejected(self, client):
        resp = client.get("/sync/status")
        assert resp.status_code == 403

    def test_garbage_token_rejected(self, client):
        resp = client.get(
            "/sync/status",
            headers={"Authorization": "Bearer invalid_token_12345"},
        )
        assert resp.status_code == 401
