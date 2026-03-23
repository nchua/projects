"""Tests for Phase 1D: Briefing Engine."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch


from app.core.security import hash_password
from app.models.action_item import ActionItem
from app.models.calendar_event import CalendarEvent
from app.models.integration import Integration
from app.models.recurring_task import RecurringTask
from app.models.user import User
from app.services.briefing_service import (
    _get_calendar_events,
    _get_integration_health,
    _get_open_action_items,
    _get_todays_tasks,
    generate_morning_briefing,
)


def _create_user(db_session, email="brief@example.com"):
    user = User(
        email=email,
        password_hash=hash_password("TestPass123"),
    )
    db_session.add(user)
    db_session.flush()
    return user


# =============================================================================
# Data Assembly Tests
# =============================================================================


class TestGetCalendarEvents:
    """Tests for calendar event retrieval."""

    def test_returns_events_for_date(self, db_session):
        user = _create_user(db_session)
        today = date.today()

        event = CalendarEvent(
            user_id=user.id,
            provider="google",
            external_id="evt-1",
            title="Team standup",
            start_time=datetime.combine(
                today, datetime.min.time()
            ).replace(hour=10, tzinfo=timezone.utc),
            end_time=datetime.combine(
                today, datetime.min.time()
            ).replace(hour=11, tzinfo=timezone.utc),
            location="Zoom",
        )
        db_session.add(event)
        db_session.flush()

        events = _get_calendar_events(
            db_session, user.id, today
        )
        assert len(events) == 1
        assert events[0].title == "Team standup"
        assert events[0].location == "Zoom"

    def test_excludes_other_dates(self, db_session):
        user = _create_user(db_session)
        yesterday = date.today() - timedelta(days=1)

        event = CalendarEvent(
            user_id=user.id,
            provider="google",
            external_id="evt-old",
            title="Yesterday's meeting",
            start_time=datetime.combine(
                yesterday, datetime.min.time()
            ).replace(hour=10, tzinfo=timezone.utc),
            end_time=datetime.combine(
                yesterday, datetime.min.time()
            ).replace(hour=11, tzinfo=timezone.utc),
        )
        db_session.add(event)
        db_session.flush()

        events = _get_calendar_events(
            db_session, user.id, date.today()
        )
        assert len(events) == 0


class TestGetTodaysTasks:
    """Tests for today's task retrieval."""

    def test_daily_tasks_always_due(self, db_session):
        user = _create_user(db_session)

        task = RecurringTask(
            user_id=user.id,
            title="Supplements",
            cadence="daily",
            priority="non_negotiable",
        )
        db_session.add(task)
        db_session.flush()

        tasks = _get_todays_tasks(
            db_session, user.id, date.today()
        )
        assert len(tasks) == 1
        assert tasks[0].title == "Supplements"

    def test_archived_tasks_excluded(self, db_session):
        user = _create_user(db_session)

        task = RecurringTask(
            user_id=user.id,
            title="Old task",
            cadence="daily",
            priority="flexible",
            is_archived=True,
        )
        db_session.add(task)
        db_session.flush()

        tasks = _get_todays_tasks(
            db_session, user.id, date.today()
        )
        assert len(tasks) == 0


class TestGetOpenActionItems:
    """Tests for open action item retrieval."""

    def test_returns_new_and_acknowledged(self, db_session):
        user = _create_user(db_session)

        for i, st in enumerate(
            ["new", "acknowledged", "dismissed", "actioned"]
        ):
            db_session.add(
                ActionItem(
                    user_id=user.id,
                    source="gmail",
                    title=f"Item {st}",
                    priority="medium",
                    status=st,
                )
            )
        db_session.flush()

        items = _get_open_action_items(db_session, user.id)
        assert len(items) == 2
        titles = [i.title for i in items]
        assert "Item new" in titles
        assert "Item acknowledged" in titles

    def test_sorts_by_priority(self, db_session):
        user = _create_user(db_session)

        for p in ["low", "high", "medium"]:
            db_session.add(
                ActionItem(
                    user_id=user.id,
                    source="gmail",
                    title=f"Item {p}",
                    priority=p,
                    status="new",
                )
            )
        db_session.flush()

        items = _get_open_action_items(db_session, user.id)
        priorities = [i.priority for i in items]
        assert priorities == ["high", "medium", "low"]


class TestGetIntegrationHealth:
    """Tests for integration health retrieval."""

    def test_returns_active_integrations(self, db_session):
        user = _create_user(db_session)

        db_session.add(
            Integration(
                user_id=user.id,
                provider="gmail",
                status="healthy",
                is_active=True,
            )
        )
        db_session.add(
            Integration(
                user_id=user.id,
                provider="github",
                status="degraded",
                is_active=True,
                last_error="rate limited",
            )
        )
        db_session.flush()

        health = _get_integration_health(db_session, user.id)
        assert len(health) == 2
        providers = {h.provider for h in health}
        assert "gmail" in providers
        assert "github" in providers

    def test_excludes_inactive(self, db_session):
        user = _create_user(db_session)

        db_session.add(
            Integration(
                user_id=user.id,
                provider="slack",
                status="disabled",
                is_active=False,
            )
        )
        db_session.flush()

        health = _get_integration_health(db_session, user.id)
        assert len(health) == 0


# =============================================================================
# Briefing Generation Tests
# =============================================================================


class TestGenerateBriefing:
    """Tests for the full briefing generation."""

    @patch(
        "app.services.briefing_service._generate_ai_insights",
        return_value=None,
    )
    def test_generates_briefing(
        self, mock_insights, db_session
    ):
        user = _create_user(db_session)
        today = date.today()

        # Add a daily task
        db_session.add(
            RecurringTask(
                user_id=user.id,
                title="Reading",
                cadence="daily",
                priority="non_negotiable",
            )
        )
        db_session.flush()

        briefing = generate_morning_briefing(
            user.id, db_session, today
        )

        assert briefing is not None
        assert briefing.date == today
        assert briefing.briefing_type == "morning"
        assert briefing.content is not None
        assert briefing.generated_at is not None

        # Content should have today's tasks
        content = briefing.content
        assert len(content["todays_tasks"]) >= 1

    @patch(
        "app.services.briefing_service._generate_ai_insights",
        return_value=None,
    )
    def test_returns_existing_briefing(
        self, mock_insights, db_session
    ):
        user = _create_user(db_session)
        today = date.today()

        # Generate first
        b1 = generate_morning_briefing(
            user.id, db_session, today
        )
        db_session.flush()
        b1_id = b1.id

        # Generate again — should return same
        b2 = generate_morning_briefing(
            user.id, db_session, today
        )
        assert b2.id == b1_id

    @patch(
        "app.services.briefing_service._generate_ai_insights",
        return_value=None,
    )
    def test_flags_integration_gaps(
        self, mock_insights, db_session
    ):
        user = _create_user(db_session)

        db_session.add(
            Integration(
                user_id=user.id,
                provider="gmail",
                status="failed",
                is_active=True,
                last_error="token expired",
            )
        )
        db_session.flush()

        briefing = generate_morning_briefing(
            user.id, db_session
        )

        assert "gmail" in briefing.integration_gaps


# =============================================================================
# Briefing API Tests
# =============================================================================


class TestBriefingAPI:
    """Tests for briefing REST endpoints."""

    def _auth_headers(self, client):
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "briefapi@example.com",
                "password": "TestPass123",
            },
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": "briefapi@example.com",
                "password": "TestPass123",
            },
        )
        return {
            "Authorization": f"Bearer {resp.json()['access_token']}"
        }

    @patch(
        "app.services.briefing_service._generate_ai_insights",
        return_value=None,
    )
    def test_get_today_generates(
        self, mock_insights, client
    ):
        headers = self._auth_headers(client)
        resp = client.get(
            "/api/v1/briefings/today", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["briefing_type"] == "morning"
        assert data["content"] is not None

    def test_get_by_date_not_found(self, client):
        headers = self._auth_headers(client)
        resp = client.get(
            "/api/v1/briefings/2020-01-01", headers=headers
        )
        assert resp.status_code == 404

    @patch(
        "app.services.briefing_service._generate_ai_insights",
        return_value=None,
    )
    def test_mark_viewed(self, mock_insights, client):
        headers = self._auth_headers(client)

        # Generate first
        client.get(
            "/api/v1/briefings/today", headers=headers
        )

        # Mark viewed
        resp = client.post(
            "/api/v1/briefings/today/viewed",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["viewed_at"] is not None

    @patch(
        "app.services.briefing_service._generate_ai_insights",
        return_value=None,
    )
    def test_preview_regenerates(
        self, mock_insights, client
    ):
        headers = self._auth_headers(client)

        # Generate initial
        r1 = client.get(
            "/api/v1/briefings/today", headers=headers
        )
        id1 = r1.json()["id"]

        # Preview forces regeneration
        r2 = client.post(
            "/api/v1/briefings/preview", headers=headers
        )
        assert r2.status_code == 200
        id2 = r2.json()["id"]
        assert id2 != id1  # New briefing generated

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/briefings/today")
        assert resp.status_code == 403
