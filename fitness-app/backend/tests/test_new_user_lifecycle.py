"""
New-user lifecycle tests (see docs/new-user-test-spec.md).

These drive the REAL HTTP endpoints (POST /auth/register + /auth/login), not the
``create_test_user`` fixture, so the genuine registration -> first-workout ->
gamification wiring is exercised end-to-end. This is the path that 500'd in prod
on 2026-06-28 (missing ``user_quests.completed_by_workout_id``); T1 is the
regression guard for it.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.exercise import Exercise

VALID_PASSWORD = "TestPass123!"  # >=12, upper+lower+digit+symbol


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _register_and_login(client, email: str, password: str = VALID_PASSWORD) -> dict:
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed_exercise(db, name: str, category: str, primary_muscle: str) -> Exercise:
    exercise = Exercise(
        id=str(uuid.uuid4()),
        name=name,
        category=category,
        primary_muscle=primary_muscle,
        secondary_muscles=["Cardio"] if category in ("Cardio", "Sport") else [],
        is_custom=False,
        user_id=None,
    )
    db.add(exercise)
    db.commit()
    return exercise


# ── T1: new user can log their first strength workout (regression guard) ──────

def test_new_user_first_strength_workout(client, db, unique_email):
    headers = _register_and_login(client, unique_email("t1"))
    bench = _seed_exercise(db, "Barbell Bench Press", "Strength", "Chest")

    r = client.post("/workouts", headers=headers, json={
        "date": _iso(datetime.now(timezone.utc)),
        "duration_minutes": 45,
        "exercises": [{
            "exercise_id": bench.id,
            "order_index": 0,
            "sets": [{"weight": 135, "weight_unit": "lb", "reps": 5, "set_number": 1}],
        }],
    })

    # The incident manifested as a 500 here (quest update on a fresh user).
    assert r.status_code == 201, r.text
    body = r.json()
    # Gamification pipeline ran for a user with no prior progress/quests.
    assert body["workout"]["id"]
    assert "xp_earned" in body and "total_xp" in body and "level" in body
    assert body["level"] >= 1


# ── T2: new user can import their first Apple-Watch cardio workout ─────────────

def test_new_user_first_cardio_import(client, db, unique_email):
    headers = _register_and_login(client, unique_email("t2"))
    _seed_exercise(db, "Running", "Cardio", "Legs")

    start = datetime.now(timezone.utc) - timedelta(minutes=45)
    r = client.post("/workouts/import-healthkit", headers=headers, json={"workouts": [{
        "hk_uuid": "NEWUSER-RUN-1",
        "activity_type": "running",
        "is_strength": False,
        "start": _iso(start),
        "end": _iso(datetime.now(timezone.utc)),
        "duration_seconds": 2700,
        "kilojoules": 1800.0,
        "avg_heart_rate": 150,
        "peak_heart_rate": 170,
        "hr_zone_seconds": {"z3": 2700},
    }]})
    assert r.status_code == 200, r.text
    assert len(r.json()["sessions_created"]) == 1

    row = next(w for w in client.get("/workouts", headers=headers).json()
               if w["activity_type"] == "running")
    assert row["is_activity"] is True
    assert row["calories"] == round(1800.0 * 0.239006)
    assert row["exertion_score"] is not None
    assert "Quads" in row["primary_muscles"]

    cooldowns = client.get("/analytics/cooldowns", headers=headers)
    assert cooldowns.status_code == 200, cooldowns.text
    cooling = {m["muscle_group"] for m in cooldowns.json()["muscles_cooling"]}
    assert "quads" in cooling


# ── T3: a brand-new user's analytics endpoints are empty, not broken ──────────

def test_new_user_empty_analytics(client, unique_email):
    headers = _register_and_login(client, unique_email("t3"))

    cooldowns = client.get("/analytics/cooldowns", headers=headers)
    assert cooldowns.status_code == 200, cooldowns.text
    assert cooldowns.json()["muscles_cooling"] == []

    progress = client.get("/progress", headers=headers)
    assert progress.status_code == 200, progress.text


# ── T4: re-registering a deleted account's email cannot resurrect/hijack it ────

def test_reregister_deleted_email_does_not_resurrect(client, unique_email):
    email = unique_email("t4")
    headers = _register_and_login(client, email)

    # Soft-delete the account (requires password confirmation).
    assert client.request("DELETE", "/auth/account", headers=headers,
                          json={"password": VALID_PASSWORD}).status_code == 204

    # Re-register the same email with a DIFFERENT password -> decoy 201, no resurrection.
    new_password = "BrandNewPass99$"
    r = client.post("/auth/register", json={"email": email, "password": new_password})
    assert r.status_code == 201, r.text

    # Neither the new nor the old password can log in to the deleted account.
    assert client.post("/auth/login", json={"email": email, "password": new_password}).status_code in (401, 403)
    assert client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD}).status_code in (401, 403)


# ── §6: validation / negative cases ───────────────────────────────────────────

def test_register_invalid_email_rejected(client):
    r = client.post("/auth/register", json={"email": "not-an-email", "password": VALID_PASSWORD})
    assert r.status_code == 422


@pytest.mark.parametrize("password,reason", [
    ("Short1!", "too short"),
    ("testpass123!", "no uppercase"),
    ("TESTPASS123!", "no lowercase"),
    ("TestPassword!", "no digit"),
    ("TestPassword12", "no symbol"),
])
def test_register_weak_password_rejected(client, unique_email, password, reason):
    r = client.post("/auth/register", json={"email": unique_email("weak"), "password": password})
    assert r.status_code == 422, f"{reason!r} should be rejected: {r.text}"
