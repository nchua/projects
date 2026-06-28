#!/usr/bin/env python3
"""Post-deploy smoke check for the fitness backend.

Verifies the new-user -> first-workout path end-to-end against the LIVE backend —
the exact flow that 500'd in the 2026-06-28 prod incident (a missing
``user_quests.completed_by_workout_id`` column, undetectable by the SQLite unit
suite which builds its schema from the models). Registers a throwaway user, logs
a strength workout AND imports a cardio workout (both run
``update_quest_progress``), exercises the read paths, then deletes the throwaway
account so nothing accumulates.

Usage:
    API_BASE_URL=https://your-backend python scripts/post_deploy_smoke.py

Exits 0 on success, 1 on any failure (so CI / cron surfaces it).
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx

BASE_URL = os.environ.get(
    "API_BASE_URL", "https://backend-production-e316.up.railway.app"
).rstrip("/")
# Throwaway credentials — satisfies the password policy (>=12, upper/lower/digit/symbol).
PASSWORD = "SmokeCheck123!"
TIMEOUT = 30.0


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def run_smoke(client: httpx.Client) -> None:
    """Run the full new-user flow; raise on the first failing step."""
    email = f"smoke-{uuid.uuid4().hex[:12]}@example.com"

    r = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, f"register: {r.status_code} {r.text}"

    r = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, f"login: {r.status_code} {r.text}"
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    try:
        exercises = client.get("/exercises", headers=headers, params={"limit": 1}).json()
        exercise_id = (exercises if isinstance(exercises, list)
                       else exercises.get("exercises", []))[0]["id"]

        # 1. Strength create — the incident path (update_quest_progress on a fresh user).
        r = client.post("/workouts", headers=headers, json={
            "date": _iso(datetime.now(timezone.utc)),
            "duration_minutes": 10,
            "exercises": [{
                "exercise_id": exercise_id, "order_index": 0,
                "sets": [{"weight": 100, "weight_unit": "lb", "reps": 5, "set_number": 1}],
            }],
        })
        assert r.status_code == 201, f"create_workout: {r.status_code} {r.text}"

        # 2. Cardio import — exercises the HealthKit + cooldown path too.
        start = datetime.now(timezone.utc) - timedelta(minutes=20)
        r = client.post("/workouts/import-healthkit", headers=headers, json={"workouts": [{
            "hk_uuid": f"SMOKE-{uuid.uuid4().hex[:8]}",
            "activity_type": "running", "is_strength": False,
            "start": _iso(start), "end": _iso(datetime.now(timezone.utc)),
            "duration_seconds": 1200, "kilojoules": 800.0, "hr_zone_seconds": {"z2": 1200},
        }]})
        assert r.status_code == 200, f"import_healthkit: {r.status_code} {r.text}"

        # 3. Read paths the incident also broke.
        assert client.get("/workouts", headers=headers).status_code == 200, "list workouts"
        assert client.get("/analytics/cooldowns", headers=headers).status_code == 200, "cooldowns"
    finally:
        # Always clean up the throwaway account, even on failure.
        try:
            client.request("DELETE", "/auth/account", headers=headers, json={"password": PASSWORD})
        except Exception:  # noqa: BLE001 — best-effort cleanup; never mask the real failure
            pass


def main() -> int:
    print(f"smoke: target {BASE_URL}")
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        try:
            run_smoke(client)
        except Exception as exc:  # noqa: BLE001 — smoke check: any failure is a fail
            print(f"SMOKE FAIL: {exc!r}", file=sys.stderr)
            return 1
    print("SMOKE PASS: new user can register, log a workout, import cardio, and delete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
