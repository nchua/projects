"""
Tests for the read-only owner export (``GET /export/workouts``).

Covers the token gate (unset → 503, wrong/missing → 401), that only the
configured account's data is served, and the volume conventions: lb tonnage,
warm-ups listed but excluded from every total, soft-deleted sessions dropped,
Monday-start weeks keyed on ``local_date``.
"""
from datetime import date, datetime, timedelta
from typing import Dict, Sequence, Tuple

import pytest

from app.api import export as export_api
from app.models.bodyweight import BodyweightEntry
from app.models.exercise import Exercise
from app.models.pr import PR, PRType
from app.models.workout import Set, WeightUnit, WorkoutExercise, WorkoutSession

TOKEN = "t" * 40
OWNER = "export-owner@example.com"


@pytest.fixture
def configured(monkeypatch) -> Dict[str, str]:
    """Export enabled for OWNER; returns the auth headers."""
    monkeypatch.setattr(export_api.settings, "EXPORT_TOKEN", TOKEN)
    monkeypatch.setattr(export_api.settings, "EXPORT_USER_EMAIL", OWNER)
    return {"Authorization": f"Bearer {TOKEN}"}


def _exercise(db, name: str, primary: str) -> Exercise:
    ex = Exercise(name=name, primary_muscle=primary, category="Push")
    db.add(ex)
    db.commit()
    return ex


def _workout(
    db,
    user_id: str,
    exercise: Exercise,
    day: date,
    sets: Sequence[Tuple[float, int, bool]],
) -> WorkoutSession:
    """A session on ``day`` with (weight_lb, reps, is_warmup) sets."""
    session = WorkoutSession(
        user_id=user_id,
        date=datetime.combine(day, datetime.min.time()),
        local_date=day,
        duration_minutes=60,
    )
    db.add(session)
    db.flush()
    we = WorkoutExercise(session_id=session.id, exercise_id=exercise.id, order_index=0)
    db.add(we)
    db.flush()
    for n, (weight, reps, warmup) in enumerate(sets, start=1):
        db.add(Set(
            workout_exercise_id=we.id, weight=weight, weight_lb=weight,
            reps=reps, set_number=n, is_warmup=warmup,
        ))
    db.commit()
    return session


class TestExportAuth:
    def test_unconfigured_is_503(self, client, monkeypatch):
        monkeypatch.setattr(export_api.settings, "EXPORT_TOKEN", "")
        resp = client.get("/export/workouts", headers={"Authorization": "Bearer anything"})
        assert resp.status_code == 503

    def test_short_token_counts_as_unconfigured(self, client, monkeypatch):
        monkeypatch.setattr(export_api.settings, "EXPORT_TOKEN", "short")
        resp = client.get("/export/workouts", headers={"Authorization": "Bearer short"})
        assert resp.status_code == 503

    def test_missing_and_wrong_token_are_401(self, client, configured, create_test_user):
        create_test_user(email=OWNER)
        assert client.get("/export/workouts").status_code == 401
        wrong = client.get("/export/workouts", headers={"Authorization": "Bearer " + "x" * 40})
        assert wrong.status_code == 401

    def test_user_jwt_is_not_accepted(self, client, configured, auth_headers):
        headers, _ = auth_headers(email=OWNER)
        assert client.get("/export/workouts", headers=headers).status_code == 401

    def test_rejected_tokens_are_rate_limited(self, client, configured, create_test_user):
        create_test_user(email=OWNER)
        bad = {"Authorization": "Bearer " + "x" * 40}
        codes = [client.get("/export/workouts", headers=bad).status_code for _ in range(31)]
        assert codes[:30] == [401] * 30
        assert codes[30] == 429

    def test_unknown_export_user_is_503(self, client, configured):
        assert client.get("/export/workouts", headers=configured).status_code == 503


class TestExportContent:
    def test_volume_excludes_warmups_and_other_users(self, client, db, configured, create_test_user):
        owner, _ = create_test_user(email=OWNER)
        other, _ = create_test_user(email="someone-else@example.com")
        bench = _exercise(db, "Export Bench", "Chest")
        squat = _exercise(db, "Export Squat", "Quads")
        today = date.today()
        _workout(db, owner.id, bench, today, [(135, 5, True), (185, 5, False), (185, 5, False)])
        _workout(db, owner.id, squat, today, [(225, 3, False)])
        _workout(db, other.id, bench, today, [(500, 10, False)])

        resp = client.get("/export/workouts", headers=configured)
        assert resp.status_code == 200, resp.json()
        body = resp.json()

        assert len(body["sessions"]) == 2
        assert len(body["sets"]) == 4  # warm-up listed, other user's set not
        warmup = next(s for s in body["sets"] if s["is_warmup"])
        assert warmup["volume_lb"] == 0

        bench_session = next(s for s in body["sessions"] if s["working_sets"] == 2)
        assert bench_session["kind"] == "strength"
        assert bench_session["tonnage_lb"] == 1850
        assert bench_session["total_reps"] == 10

        monday = (today - timedelta(days=today.weekday())).isoformat()
        assert body["weekly_volume"] == [{
            "week_start": monday,
            "strength_sessions": 2,
            "cardio_sessions": 0,
            "working_sets": 3,
            "total_reps": 13,
            "tonnage_lb": 2525.0,
            "cardio_miles": 0.0,
        }]
        by_muscle = {m["primary_muscle"]: m for m in body["weekly_muscle_volume"]}
        assert by_muscle["Chest"]["working_sets"] == 2
        assert by_muscle["Chest"]["tonnage_lb"] == 1850
        assert by_muscle["Quads"]["tonnage_lb"] == 675

    def test_deleted_and_out_of_window_sessions_are_dropped(
        self, client, db, configured, create_test_user,
    ):
        owner, _ = create_test_user(email=OWNER)
        bench = _exercise(db, "Export Bench 2", "Chest")
        today = date.today()
        _workout(db, owner.id, bench, today - timedelta(days=3), [(185, 5, False)])
        _workout(db, owner.id, bench, today - timedelta(days=40), [(175, 5, False)])
        gone = _workout(db, owner.id, bench, today - timedelta(days=2), [(999, 1, False)])
        gone.deleted_at = datetime.now()
        db.commit()

        body = client.get("/export/workouts?days=14", headers=configured).json()

        assert [s["tonnage_lb"] for s in body["sessions"]] == [925]
        assert body["sessions"][0]["day"] == (today - timedelta(days=3)).isoformat()

    def test_cardio_and_bodyweight_rows(self, client, db, configured, create_test_user):
        owner, _ = create_test_user(email=OWNER)
        today = date.today()
        db.add(WorkoutSession(
            user_id=owner.id, date=datetime.combine(today, datetime.min.time()),
            local_date=today, activity_type="Outdoor Run", distance_meters=1609.344 * 3,
        ))
        db.add(BodyweightEntry(user_id=owner.id, date=today, weight_lb=160.4, source="manual"))
        # Watch imports attach a set-less placeholder exercise; still cardio.
        walk = WorkoutSession(
            user_id=owner.id, date=datetime.combine(today, datetime.min.time()),
            local_date=today, activity_type="walking", distance_meters=1609.344,
        )
        db.add(walk)
        db.flush()
        placeholder = _exercise(db, "Export Walking", "Cardio")
        db.add(WorkoutExercise(session_id=walk.id, exercise_id=placeholder.id, order_index=0))
        db.commit()

        body = client.get("/export/workouts", headers=configured).json()

        assert [s["kind"] for s in body["sessions"]] == ["cardio", "cardio"]
        run = next(s for s in body["sessions"] if s["activity_type"] == "Outdoor Run")
        assert run["distance_miles"] == 3.0
        assert body["weekly_volume"][0]["strength_sessions"] == 0
        assert body["weekly_volume"][0]["cardio_sessions"] == 2
        assert body["weekly_volume"][0]["cardio_miles"] == 4.0
        assert body["bodyweight"] == [
            {"day": today.isoformat(), "weight_lb": 160.4, "source": "manual"}
        ]

    def test_day_follows_local_date_and_kg_is_normalized(
        self, client, db, configured, create_test_user,
    ):
        owner, _ = create_test_user(email=OWNER)
        bench = _exercise(db, "Export Bench 3", "Chest")
        sunday = date.today() - timedelta(days=date.today().weekday() + 1)
        # Evening lift stored as a UTC instant on Monday; the lifter's day was Sunday.
        session = WorkoutSession(
            user_id=owner.id,
            date=datetime.combine(sunday + timedelta(days=1), datetime.min.time())
            + timedelta(hours=3),
            local_date=sunday,
        )
        db.add(session)
        db.flush()
        we = WorkoutExercise(session_id=session.id, exercise_id=bench.id, order_index=0)
        db.add(we)
        db.flush()
        kg_set = Set(
            workout_exercise_id=we.id, weight=100, weight_unit=WeightUnit.KG,
            weight_lb=None, reps=5, set_number=1,
        )
        db.add(kg_set)
        db.flush()
        db.add(PR(
            user_id=owner.id, exercise_id=bench.id, set_id=kg_set.id,
            pr_type=PRType.REP_PR, weight=100, reps=5, achieved_at=session.date,
        ))
        db.commit()

        body = client.get("/export/workouts", headers=configured).json()

        row = body["sets"][0]
        assert row["day"] == sunday.isoformat()
        assert row["week_start"] == (sunday - timedelta(days=6)).isoformat()
        assert row["weight_lb"] == 220.46
        assert body["prs"] == [{
            "day": sunday.isoformat(), "exercise": "Export Bench 3", "pr_type": "rep_pr",
            "e1rm": None, "weight_lb": 220.46, "reps": 5,
        }]

    def test_prs_of_deleted_sessions_are_dropped(self, client, db, configured, create_test_user):
        owner, _ = create_test_user(email=OWNER)
        bench = _exercise(db, "Export Bench 4", "Chest")
        session = _workout(db, owner.id, bench, date.today(), [(200, 3, False)])
        top = db.query(Set).join(WorkoutExercise).filter(
            WorkoutExercise.session_id == session.id).one()
        db.add(PR(
            user_id=owner.id, exercise_id=bench.id, set_id=top.id,
            pr_type=PRType.E1RM, value=220.0, achieved_at=session.date,
        ))
        db.commit()
        assert len(client.get("/export/workouts", headers=configured).json()["prs"]) == 1

        session.deleted_at = datetime.now()
        db.commit()

        assert client.get("/export/workouts", headers=configured).json()["prs"] == []
