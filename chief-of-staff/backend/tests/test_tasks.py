"""Tests for Phase 1E: Task Management API."""


from app.core.security import hash_password
from app.models.user import User
from app.services.onboarding_service import create_default_tasks


# =============================================================================
# Recurring Tasks API Tests
# =============================================================================


class TestRecurringTasksAPI:
    """Tests for recurring task endpoints."""

    def _auth_headers(self, client):
        client.post("/api/v1/auth/register", json={
            "email": "tasks@example.com",
            "password": "TestPass123",
        })
        resp = client.post("/api/v1/auth/login", json={
            "email": "tasks@example.com",
            "password": "TestPass123",
        })
        return {
            "Authorization": f"Bearer {resp.json()['access_token']}"
        }

    def test_list_empty(self, client):
        headers = self._auth_headers(client)
        resp = client.get(
            "/api/v1/tasks/recurring", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_task(self, client):
        headers = self._auth_headers(client)
        resp = client.post(
            "/api/v1/tasks/recurring",
            json={
                "title": "Supplements",
                "cadence": "daily",
                "priority": "non_negotiable",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Supplements"
        assert data["cadence"] == "daily"
        assert data["streak_count"] == 0

    def test_update_task(self, client):
        headers = self._auth_headers(client)
        create = client.post(
            "/api/v1/tasks/recurring",
            json={"title": "Old", "cadence": "daily"},
            headers=headers,
        )
        task_id = create.json()["id"]

        resp = client.put(
            f"/api/v1/tasks/recurring/{task_id}",
            json={"title": "New Title"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"

    def test_archive_task(self, client):
        headers = self._auth_headers(client)
        create = client.post(
            "/api/v1/tasks/recurring",
            json={"title": "Archive me", "cadence": "daily"},
            headers=headers,
        )
        task_id = create.json()["id"]

        resp = client.delete(
            f"/api/v1/tasks/recurring/{task_id}",
            headers=headers,
        )
        assert resp.status_code == 204

        # Should not appear in default list
        list_resp = client.get(
            "/api/v1/tasks/recurring", headers=headers
        )
        ids = [t["id"] for t in list_resp.json()]
        assert task_id not in ids

        # Should appear with include_archived
        list_resp2 = client.get(
            "/api/v1/tasks/recurring?include_archived=true",
            headers=headers,
        )
        ids2 = [t["id"] for t in list_resp2.json()]
        assert task_id in ids2

    def test_complete_task(self, client):
        headers = self._auth_headers(client)
        create = client.post(
            "/api/v1/tasks/recurring",
            json={"title": "Complete me", "cadence": "daily"},
            headers=headers,
        )
        task_id = create.json()["id"]

        resp = client.post(
            f"/api/v1/tasks/recurring/{task_id}/complete",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed_at"] is not None
        assert data["skipped"] is False

    def test_complete_twice_fails(self, client):
        headers = self._auth_headers(client)
        create = client.post(
            "/api/v1/tasks/recurring",
            json={"title": "Double", "cadence": "daily"},
            headers=headers,
        )
        task_id = create.json()["id"]

        client.post(
            f"/api/v1/tasks/recurring/{task_id}/complete",
            headers=headers,
        )
        resp = client.post(
            f"/api/v1/tasks/recurring/{task_id}/complete",
            headers=headers,
        )
        assert resp.status_code == 409

    def test_skip_task(self, client):
        headers = self._auth_headers(client)
        create = client.post(
            "/api/v1/tasks/recurring",
            json={"title": "Skip me", "cadence": "daily"},
            headers=headers,
        )
        task_id = create.json()["id"]

        resp = client.post(
            f"/api/v1/tasks/recurring/{task_id}/skip",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["skipped"] is True

    def test_streak_starts_at_one(self, client):
        headers = self._auth_headers(client)
        create = client.post(
            "/api/v1/tasks/recurring",
            json={"title": "Streak", "cadence": "daily"},
            headers=headers,
        )
        task_id = create.json()["id"]

        client.post(
            f"/api/v1/tasks/recurring/{task_id}/complete",
            headers=headers,
        )
        # Check the task's streak
        task = client.get(
            "/api/v1/tasks/recurring", headers=headers
        ).json()
        streak_task = [
            t for t in task if t["id"] == task_id
        ][0]
        assert streak_task["streak_count"] == 1

    def test_nonexistent_task(self, client):
        headers = self._auth_headers(client)
        resp = client.put(
            "/api/v1/tasks/recurring/nonexistent",
            json={"title": "X"},
            headers=headers,
        )
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/tasks/recurring")
        assert resp.status_code == 403


# =============================================================================
# Reminders API Tests
# =============================================================================


class TestRemindersAPI:
    """Tests for reminder endpoints."""

    def _auth_headers(self, client):
        client.post("/api/v1/auth/register", json={
            "email": "reminders@example.com",
            "password": "TestPass123",
        })
        resp = client.post("/api/v1/auth/login", json={
            "email": "reminders@example.com",
            "password": "TestPass123",
        })
        return {
            "Authorization": f"Bearer {resp.json()['access_token']}"
        }

    def test_list_empty(self, client):
        headers = self._auth_headers(client)
        resp = client.get(
            "/api/v1/reminders", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_reminder(self, client):
        headers = self._auth_headers(client)
        resp = client.post(
            "/api/v1/reminders",
            json={
                "title": "Call dentist",
                "trigger_type": "time",
                "trigger_config": {
                    "date": "2026-03-25",
                    "time": "15:00",
                },
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Call dentist"
        assert data["status"] == "pending"

    def test_complete_reminder(self, client):
        headers = self._auth_headers(client)
        create = client.post(
            "/api/v1/reminders",
            json={
                "title": "Do thing",
                "trigger_type": "time",
            },
            headers=headers,
        )
        rid = create.json()["id"]

        resp = client.post(
            f"/api/v1/reminders/{rid}/complete",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"
        assert resp.json()["completed_at"] is not None

    def test_dismiss_reminder(self, client):
        headers = self._auth_headers(client)
        create = client.post(
            "/api/v1/reminders",
            json={
                "title": "Dismiss me",
                "trigger_type": "follow_up",
            },
            headers=headers,
        )
        rid = create.json()["id"]

        resp = client.post(
            f"/api/v1/reminders/{rid}/dismiss",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"

    def test_delete_reminder(self, client):
        headers = self._auth_headers(client)
        create = client.post(
            "/api/v1/reminders",
            json={
                "title": "Delete me",
                "trigger_type": "time",
            },
            headers=headers,
        )
        rid = create.json()["id"]

        resp = client.delete(
            f"/api/v1/reminders/{rid}", headers=headers
        )
        assert resp.status_code == 204

    def test_nonexistent_reminder(self, client):
        headers = self._auth_headers(client)
        resp = client.post(
            "/api/v1/reminders/nonexistent/complete",
            headers=headers,
        )
        assert resp.status_code == 404


# =============================================================================
# Unified Tasks + Onboarding Tests
# =============================================================================


class TestUnifiedTasks:
    """Tests for the unified tasks endpoint."""

    def _auth_headers(self, client):
        client.post("/api/v1/auth/register", json={
            "email": "unified@example.com",
            "password": "TestPass123",
        })
        resp = client.post("/api/v1/auth/login", json={
            "email": "unified@example.com",
            "password": "TestPass123",
        })
        return {
            "Authorization": f"Bearer {resp.json()['access_token']}"
        }

    def test_today_returns_structure(self, client):
        headers = self._auth_headers(client)
        resp = client.get(
            "/api/v1/tasks/today", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "date" in data
        assert "recurring_tasks" in data
        assert "reminders" in data
        assert "action_items" in data

    def test_all_returns_structure(self, client):
        headers = self._auth_headers(client)
        resp = client.get(
            "/api/v1/tasks/all", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "recurring_tasks" in data
        assert "action_items" in data
        assert "reminders" in data

    def test_all_filtered_by_type(self, client):
        headers = self._auth_headers(client)
        resp = client.get(
            "/api/v1/tasks/all?task_type=recurring",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "recurring_tasks" in data
        assert "action_items" not in data


class TestOnboardingService:
    """Tests for the onboarding default tasks."""

    def test_creates_default_tasks(self, db_session):
        user = User(
            email="onboard@example.com",
            password_hash=hash_password("TestPass123"),
        )
        db_session.add(user)
        db_session.flush()

        tasks = create_default_tasks(user.id, db_session)
        assert len(tasks) == 4
        titles = [t.title for t in tasks]
        assert "Supplements" in titles
        assert "Reading" in titles
        assert "Writing" in titles
        assert "Coding" in titles

    def test_default_tasks_are_daily(self, db_session):
        user = User(
            email="onboard2@example.com",
            password_hash=hash_password("TestPass123"),
        )
        db_session.add(user)
        db_session.flush()

        tasks = create_default_tasks(user.id, db_session)
        for task in tasks:
            assert task.cadence == "daily"
            assert task.priority == "non_negotiable"
