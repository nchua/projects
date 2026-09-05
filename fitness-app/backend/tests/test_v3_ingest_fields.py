"""
ARISE v3 §7.5 / §15.2 ingest contract: duration_seconds, is_bodyweight,
is_warmup, weight_lb, kg → lb e1RM, warm-up exclusion, and the ingest hook
seam on POST /workouts and POST /sync.
"""
from datetime import date

import pytest

from app.models.exercise import Exercise
from app.models.pr import PR
from app.models.workout import Set, WorkoutExercise, WorkoutSession

KG_TO_LB = 2.20462


@pytest.fixture
def bench(db):
    ex = Exercise(name="Barbell Bench Press", is_custom=False, category="Push")
    db.add(ex)
    db.commit()
    return ex


def _payload(exercise_id: str, sets: list, **extra) -> dict:
    body = {
        "date": "2026-09-01",
        "exercises": [{"exercise_id": exercise_id, "order_index": 0, "sets": sets}],
    }
    body.update(extra)
    return body


def _db_sets(db, session_id: str) -> list:
    return (
        db.query(Set)
        .join(WorkoutExercise, WorkoutExercise.id == Set.workout_exercise_id)
        .filter(WorkoutExercise.session_id == session_id)
        .order_by(Set.set_number)
        .all()
    )


class TestPostWorkouts:
    def test_persists_duration_seconds_and_set_flags(self, client, db, auth_headers, unique_email, bench):
        headers, user = auth_headers(email=unique_email("v3-post"))
        resp = client.post("/workouts", json=_payload(bench.id, [
            {"weight": 0, "reps": 12, "set_number": 1, "is_bodyweight": True},
            {"weight": 95, "reps": 10, "set_number": 2, "is_warmup": True},
            {"weight": 135, "reps": 5, "set_number": 3},
        ], duration_seconds=3725, planned_hunt_id="ph-123"), headers=headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()

        session = db.query(WorkoutSession).filter(WorkoutSession.id == body["workout"]["id"]).first()
        assert session.duration_seconds == 3725
        assert session.duration_minutes == 62  # derived when the client sent only seconds

        rows = _db_sets(db, session.id)
        assert [r.is_bodyweight for r in rows] == [True, False, False]
        assert [r.is_warmup for r in rows] == [False, True, False]
        assert [r.weight_lb for r in rows] == [0, 95, 135]

        api_sets = body["workout"]["exercises"][0]["sets"]
        assert [s["weight_lb"] for s in api_sets] == [0, 95, 135]
        assert [s["is_bodyweight"] for s in api_sets] == [True, False, False]
        assert [s["is_warmup"] for s in api_sets] == [False, True, False]
        # Hook is a no-op until W1 wires the linker.
        assert body["planned_hunt_id"] is None
        assert body["planned_hunt_status"] is None

    def test_explicit_minutes_win_over_derived(self, client, db, auth_headers, unique_email, bench):
        headers, _ = auth_headers(email=unique_email("v3-mins"))
        resp = client.post("/workouts", json=_payload(bench.id, [
            {"weight": 135, "reps": 5, "set_number": 1},
        ], duration_seconds=3725, duration_minutes=45), headers=headers)
        assert resp.status_code == 201, resp.text
        session = db.query(WorkoutSession).filter(WorkoutSession.id == resp.json()["workout"]["id"]).first()
        assert (session.duration_minutes, session.duration_seconds) == (45, 3725)

    def test_kg_set_yields_lb_weight_and_e1rm(self, client, db, auth_headers, unique_email, bench):
        headers, _ = auth_headers(email=unique_email("v3-kg"))
        resp = client.post("/workouts", json=_payload(bench.id, [
            {"weight": 100, "weight_unit": "kg", "reps": 5, "set_number": 1},
        ]), headers=headers)
        assert resp.status_code == 201, resp.text
        (row,) = _db_sets(db, resp.json()["workout"]["id"])
        assert row.weight == 100
        assert row.weight_lb == pytest.approx(100 * KG_TO_LB, abs=0.01)
        # Epley on the lb weight: 220.46 * (1 + 5/30)
        assert row.e1rm == pytest.approx(100 * KG_TO_LB * (1 + 5 / 30), abs=0.05)
        assert resp.json()["workout"]["exercises"][0]["sets"][0]["e1rm"] > 250

    def test_warmups_mint_no_prs_and_earn_no_volume(self, client, db, auth_headers, unique_email, bench):
        headers, user = auth_headers(email=unique_email("v3-warm"))
        resp = client.post("/workouts", json=_payload(bench.id, [
            {"weight": 300, "reps": 5, "set_number": 1, "is_warmup": True},
            {"weight": 135, "reps": 5, "set_number": 2},
        ]), headers=headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()

        prs = db.query(PR).filter(PR.user_id == user.id).all()
        warmup_id = _db_sets(db, body["workout"]["id"])[0].id
        assert prs, "the working set should still mint PRs"
        assert all(pr.set_id != warmup_id for pr in prs)
        e1rm_prs = [pr for pr in prs if pr.pr_type.value == "e1rm"]
        assert e1rm_prs and e1rm_prs[0].value == pytest.approx(135 * (1 + 5 / 30), abs=0.05)

        # 300×5 = 1500 lb of warm-up volume would have earned a volume bonus.
        assert body["xp_breakdown"].get("volume_bonus", 0) == 0

    def test_hook_result_is_merged_into_response(self, client, auth_headers, unique_email, bench, monkeypatch):
        import app.api.workouts as workouts_api

        calls = []

        def fake_hook(db, session, *, planned_hunt_id=None):
            calls.append((session.id, planned_hunt_id, len(session.workout_exercises)))
            return {"planned_hunt_id": "ph-1", "planned_hunt_status": "done"}

        monkeypatch.setattr(workouts_api, "on_workout_ingested", fake_hook)
        headers, _ = auth_headers(email=unique_email("v3-hook"))
        resp = client.post("/workouts", json=_payload(bench.id, [
            {"weight": 135, "reps": 5, "set_number": 1},
        ], planned_hunt_id="ph-1"), headers=headers)
        assert resp.status_code == 201, resp.text
        assert resp.json()["planned_hunt_id"] == "ph-1"
        assert resp.json()["planned_hunt_status"] == "done"
        assert calls == [(resp.json()["workout"]["id"], "ph-1", 1)]


class TestSync:
    def test_sync_persists_v3_fields_and_calls_hook(self, client, db, auth_headers, unique_email, bench, monkeypatch):
        import app.api.sync as sync_api

        calls = []

        def fake_hook(db, session, *, planned_hunt_id=None):
            calls.append((session.id, planned_hunt_id, len(session.workout_exercises[0].sets)))
            return {}

        monkeypatch.setattr(sync_api, "on_workout_ingested", fake_hook)
        headers, user = auth_headers(email=unique_email("v3-sync"))
        workout = _payload(bench.id, [
            {"weight": 60, "weight_unit": "kg", "reps": 8, "set_number": 1, "is_warmup": True},
            {"weight": 80, "weight_unit": "kg", "reps": 5, "set_number": 2, "is_bodyweight": False},
        ], duration_seconds=1800, planned_hunt_id="ph-sync", date=date(2026, 8, 30).isoformat())
        resp = client.post("/sync", json={
            "workouts": [workout],
            "client_timestamp": "2026-08-30T12:00:00Z",
        }, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["workouts_synced"] == 1

        session = db.query(WorkoutSession).filter(WorkoutSession.user_id == user.id).first()
        assert (session.duration_seconds, session.duration_minutes) == (1800, 30)
        warm, work = _db_sets(db, session.id)
        assert warm.is_warmup is True and work.is_warmup is False
        assert work.weight_lb == pytest.approx(80 * KG_TO_LB, abs=0.01)
        assert work.e1rm == pytest.approx(80 * KG_TO_LB * (1 + 5 / 30), abs=0.05)

        prs = db.query(PR).filter(PR.user_id == user.id).all()
        assert prs and all(pr.set_id != warm.id for pr in prs)
        assert calls == [(session.id, "ph-sync", 2)]
