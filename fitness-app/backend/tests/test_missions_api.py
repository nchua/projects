"""
End-to-end tests for the missions API + goal progress pipeline.

These hit the real FastAPI endpoints via TestClient with the SQLite test DB
from conftest.py (no mocks for the service or ORM layer):

- GET  /missions/current   — weekly mission auto-generation (Sun/Mon only),
                             junction rows, persisted prescriptions, and
                             same-week idempotency
- POST /missions/{id}/accept — accept flow, double-accept, and expiry
- POST /workouts           — goal auto-completion + GoalProgressSnapshot
                             recording via update_goal_progress()

NOTE: app/api/missions.py:61 has a catch-all that silently returns
``needs_goal_setup=True`` on ANY exception. The tests assert
``needs_goal_setup is False`` with the full body in the failure message so a
swallowed generation error surfaces loudly instead of passing vacuously.
"""
from datetime import date, timedelta

import pytest

from app.models.exercise import Exercise
from app.models.mission import (
    ExercisePrescription,
    Goal,
    GoalProgressSnapshot,
    GoalStatus,
    MissionGoal,
    MissionStatus,
    MissionWorkout,
    WeeklyMission,
)
from app.services import mission_service


@pytest.fixture(autouse=True)
def _clear_exercise_id_cache():
    """
    mission_service._exercise_id_cache is a module-level global keyed by
    exercise name. Other test modules can pollute it (e.g. with Mock ids), and
    stale ids from a rolled-back transaction would poison lookups here — clear
    it around every test.
    """
    mission_service._exercise_id_cache.clear()
    yield
    mission_service._exercise_id_cache.clear()


def _seed_exercise(
    db,
    *,
    id: str = "ex-bench-001",
    name: str = "Barbell Bench Press",
    category: str = "compound",
) -> Exercise:
    """Insert an exercise row into the test DB and return it."""
    exercise = Exercise(id=id, name=name, category=category)
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise


def _goal_payload(exercise_id: str, *, target_weight: float = 225, target_reps: int = 1) -> dict:
    return {
        "exercise_id": exercise_id,
        "target_weight": target_weight,
        "target_reps": target_reps,
        "weight_unit": "lb",
        "deadline": (date.today() + timedelta(weeks=12)).isoformat(),
    }


def _workout_payload(exercise_id: str, *, weight: float, reps: int) -> dict:
    return {
        "date": date.today().isoformat(),
        "duration_minutes": 45,
        "exercises": [
            {
                "exercise_id": exercise_id,
                "order_index": 0,
                "sets": [
                    {"weight": weight, "weight_unit": "lb", "reps": reps, "set_number": 1}
                ],
            }
        ],
    }


def _monday_of_current_week() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def _patch_today(monkeypatch, day: date) -> None:
    """Pin mission_service's notion of 'today' (auto-generation runs Sun/Mon only)."""
    monkeypatch.setattr(mission_service, "get_today_utc", lambda: day)


def _get_current_mission(client, headers) -> dict:
    """GET /missions/current and fail loudly if the silent catch-all fired."""
    resp = client.get("/missions/current", headers=headers)
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    # If needs_goal_setup flips to True despite active goals, the endpoint's
    # blanket except swallowed a real generation error — debug that, don't
    # accept the fallback.
    assert body["needs_goal_setup"] is False, body
    assert body["has_active_goals"] is True, body
    assert body["mission"] is not None, body
    return body


class TestGetCurrentMission:
    def test_monday_generation_persists_and_is_idempotent(
        self, client, db, auth_headers, monkeypatch
    ):
        """
        With 3 active goals (push/pull/legs), the Monday GET generates a PPL
        mission with junction rows and persisted, weighted prescriptions —
        and a second GET the same week returns the SAME mission.
        """
        headers, _user = auth_headers()
        bench = _seed_exercise(db, id="ex-bench-001", name="Barbell Bench Press")
        deadlift = _seed_exercise(db, id="ex-dead-001", name="Barbell Deadlift")
        squat = _seed_exercise(db, id="ex-squat-001", name="Barbell Back Squat")

        goal_ids = set()
        for ex in (bench, deadlift, squat):
            resp = client.post("/goals", json=_goal_payload(ex.id), headers=headers)
            assert resp.status_code == 201, resp.json()
            goal_ids.add(resp.json()["id"])

        monday = _monday_of_current_week()
        _patch_today(monkeypatch, monday)

        body = _get_current_mission(client, headers)
        mission = body["mission"]

        assert mission["status"] == MissionStatus.OFFERED.value
        assert mission["training_split"] == "ppl"
        assert mission["goal_count"] == 3
        assert mission["week_start"] == monday.isoformat()
        assert mission["week_end"] == (monday + timedelta(days=6)).isoformat()
        assert mission["xp_reward"] == 50 + 50 * 3  # 50 base + 50 per goal
        assert len(mission["workouts"]) == 3
        assert all(w["exercise_count"] >= 1 for w in mission["workouts"])

        # Junction rows persisted — one MissionGoal per active goal.
        junction_rows = db.query(MissionGoal).filter(
            MissionGoal.mission_id == mission["id"]
        ).all()
        assert {mg.goal_id for mg in junction_rows} == goal_ids
        assert len(junction_rows) == 3

        # Prescriptions persisted with weights (85%-of-target fallback since
        # the goals have no e1RM history). Only the 3 primary lifts exist —
        # accessory template exercises weren't seeded, so they're skipped.
        prescriptions = (
            db.query(ExercisePrescription)
            .join(MissionWorkout, ExercisePrescription.mission_workout_id == MissionWorkout.id)
            .filter(MissionWorkout.mission_id == mission["id"])
            .all()
        )
        assert {p.exercise_id for p in prescriptions} == {bench.id, deadlift.id, squat.id}
        assert all(p.weight is not None and p.weight > 0 for p in prescriptions)

        # Idempotent within the same week: no second mission is generated.
        second = _get_current_mission(client, headers)
        assert second["mission"]["id"] == mission["id"]
        assert db.query(WeeklyMission).filter(
            WeeklyMission.week_start == monday
        ).count() == 1


class TestAcceptMission:
    def _generate_mission(self, client, db, headers, monkeypatch) -> tuple[str, date]:
        """Seed a goal, pin today to Monday, and return (mission_id, monday)."""
        ex = _seed_exercise(db, id="ex-bench-001", name="Barbell Bench Press")
        resp = client.post("/goals", json=_goal_payload(ex.id), headers=headers)
        assert resp.status_code == 201, resp.json()

        monday = _monday_of_current_week()
        _patch_today(monkeypatch, monday)
        body = _get_current_mission(client, headers)
        return body["mission"]["id"], monday

    def test_accept_sets_status_and_double_accept_is_400(
        self, client, db, auth_headers, monkeypatch
    ):
        headers, _user = auth_headers()
        mission_id, _monday = self._generate_mission(client, db, headers, monkeypatch)

        resp = client.post(f"/missions/{mission_id}/accept", headers=headers)

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["success"] is True
        assert body["mission"]["status"] == MissionStatus.ACCEPTED.value

        row = db.query(WeeklyMission).filter(WeeklyMission.id == mission_id).first()
        assert row.status == MissionStatus.ACCEPTED.value
        assert row.accepted_at is not None

        # Accepting an already-accepted mission is rejected.
        second = client.post(f"/missions/{mission_id}/accept", headers=headers)
        assert second.status_code == 400
        assert "cannot be accepted" in second.json()["detail"]

    def test_accept_after_week_end_returns_400_and_expires_mission(
        self, client, db, auth_headers, monkeypatch
    ):
        headers, _user = auth_headers()
        mission_id, monday = self._generate_mission(client, db, headers, monkeypatch)

        # Move "today" past week_end (Sunday) before accepting.
        _patch_today(monkeypatch, monday + timedelta(days=8))

        resp = client.post(f"/missions/{mission_id}/accept", headers=headers)

        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

        row = db.query(WeeklyMission).filter(WeeklyMission.id == mission_id).first()
        assert row.status == MissionStatus.EXPIRED.value


class TestGoalAutoCompletionViaWorkouts:
    """POST /workouts → update_goal_progress() → goal completion + snapshots."""

    def test_workout_meeting_target_e1rm_completes_goal(self, client, db, auth_headers):
        headers, _user = auth_headers()
        ex = _seed_exercise(db, id="ex-bench-001", name="Barbell Bench Press")
        goal_id = client.post(
            "/goals", json=_goal_payload(ex.id, target_weight=200), headers=headers
        ).json()["id"]

        # 205 x 1 → e1RM 205 ≥ target e1RM 200 → goal auto-completes.
        resp = client.post(
            "/workouts", json=_workout_payload(ex.id, weight=205, reps=1), headers=headers
        )
        assert resp.status_code == 201, resp.json()
        workout_id = resp.json()["workout"]["id"]

        goal = db.query(Goal).filter(Goal.id == goal_id).first()
        assert goal.status == GoalStatus.COMPLETED.value
        assert goal.achieved_at is not None
        assert goal.current_e1rm == 205

        snapshots = db.query(GoalProgressSnapshot).filter(
            GoalProgressSnapshot.goal_id == goal_id
        ).all()
        assert len(snapshots) == 1
        assert snapshots[0].e1rm == 205
        assert snapshots[0].weight == 205
        assert snapshots[0].reps == 1
        assert snapshots[0].workout_id == workout_id

    def test_lower_e1rm_records_snapshot_but_goal_stays_active(
        self, client, db, auth_headers
    ):
        headers, _user = auth_headers()
        ex = _seed_exercise(db, id="ex-squat-001", name="Barbell Back Squat")
        goal_id = client.post(
            "/goals", json=_goal_payload(ex.id, target_weight=300), headers=headers
        ).json()["id"]

        # 150 x 1 → e1RM 150 < target 300: snapshot recorded, goal still active.
        first = client.post(
            "/workouts", json=_workout_payload(ex.id, weight=150, reps=1), headers=headers
        )
        assert first.status_code == 201, first.json()

        goal = db.query(Goal).filter(Goal.id == goal_id).first()
        assert goal.status == GoalStatus.ACTIVE.value
        assert goal.achieved_at is None
        assert goal.current_e1rm == 150

        # A weaker follow-up session still gets a snapshot (for plateau /
        # regression charting) but current_e1rm never decreases.
        second = client.post(
            "/workouts", json=_workout_payload(ex.id, weight=140, reps=1), headers=headers
        )
        assert second.status_code == 201, second.json()

        snapshots = (
            db.query(GoalProgressSnapshot)
            .filter(GoalProgressSnapshot.goal_id == goal_id)
            .order_by(GoalProgressSnapshot.recorded_at)
            .all()
        )
        assert len(snapshots) == 2
        assert {s.e1rm for s in snapshots} == {150, 140}

        goal = db.query(Goal).filter(Goal.id == goal_id).first()
        assert goal.status == GoalStatus.ACTIVE.value
        assert goal.current_e1rm == 150  # did not drop to 140
