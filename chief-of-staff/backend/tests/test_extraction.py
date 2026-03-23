"""Tests for Phase 1C: AI Extraction Pipeline."""


import pytest

from app.core.security import hash_password
from app.models.action_item import ActionItem
from app.models.enums import (
    DismissReason,
)
from app.models.user import User
from app.services.email_preprocessor import (
    hash_content,
    html_to_text,
    preprocess_body,
    strip_email_noise,
    truncate_for_api,
)
from app.services.extraction_service import (
    _clamp,
    _normalize_priority,
    process_github_notifications,
)
from app.services.feedback_service import (
    dismiss_action_item,
    get_dismissal_stats,
)


# =============================================================================
# Email Preprocessor Tests
# =============================================================================


class TestEmailPreprocessor:
    """Tests for the email preprocessor module."""

    def test_strip_email_noise_none(self):
        assert strip_email_noise(None) == ""

    def test_strip_email_noise_empty(self):
        assert strip_email_noise("") == ""

    def test_strip_email_noise_html_tags(self):
        text = "<p>Hello <b>world</b></p>"
        result = strip_email_noise(text)
        assert "<p>" not in result
        assert "Hello" in result
        assert "world" in result

    def test_strip_email_noise_quoted_reply(self):
        text = "Important\n\nOn Mon, Jan 1 wrote:\nOld stuff"
        result = strip_email_noise(text)
        assert "Important" in result
        # Quoted reply should be removed
        assert "Old stuff" not in result

    def test_strip_email_noise_signature(self):
        text = "Real content\n--\nJohn Doe\nSr. Engineer"
        result = strip_email_noise(text)
        assert "Real content" in result
        assert "John Doe" not in result

    def test_strip_email_noise_unsubscribe(self):
        text = "Content\nClick to unsubscribe from this"
        result = strip_email_noise(text)
        assert "Content" in result
        assert "unsubscribe" not in result

    def test_strip_email_noise_html_entities(self):
        text = "Tom &amp; Jerry &lt;show&gt;"
        result = strip_email_noise(text)
        assert "Tom & Jerry <show>" == result

    def test_html_to_text_basic(self):
        assert "Hello world" in html_to_text(
            "<p>Hello <b>world</b></p>"
        )

    def test_html_to_text_strips_scripts(self):
        html = "<p>Hi</p><script>alert('x')</script><p>there</p>"
        text = html_to_text(html)
        assert "alert" not in text
        assert "Hi" in text

    def test_truncate_short(self):
        assert truncate_for_api("short") == "short"

    def test_truncate_long(self):
        text = "word " * 2000  # ~10000 chars
        result = truncate_for_api(text, max_chars=100)
        assert result.endswith("[truncated]")
        assert len(result) < 200

    def test_truncate_at_word_boundary(self):
        text = "hello world " * 100
        result = truncate_for_api(text, max_chars=50)
        # Should not cut mid-word
        assert not result.split("\n")[0].endswith("hel")

    def test_preprocess_body_combines(self):
        raw = "<p>Content</p>\n--\nSig\n" + "x " * 5000
        result = preprocess_body(raw, max_chars=100)
        assert "Content" in result
        assert "Sig" not in result
        assert len(result) < 200

    def test_hash_content_deterministic(self):
        h1 = hash_content("test")
        h2 = hash_content("test")
        assert h1 == h2

    def test_hash_content_differs(self):
        assert hash_content("a") != hash_content("b")


# =============================================================================
# Extraction Service Helper Tests
# =============================================================================


class TestExtractionHelpers:
    """Tests for extraction service helper functions."""

    def test_clamp_within_range(self):
        assert _clamp(0.5, 0.0, 1.0) == 0.5

    def test_clamp_below(self):
        assert _clamp(-1.0, 0.0, 1.0) == 0.0

    def test_clamp_above(self):
        assert _clamp(2.0, 0.0, 1.0) == 1.0

    def test_normalize_priority_valid(self):
        assert _normalize_priority("high") == "high"
        assert _normalize_priority("MEDIUM") == "medium"
        assert _normalize_priority(" low ") == "low"

    def test_normalize_priority_invalid(self):
        assert _normalize_priority("urgent") == "medium"
        assert _normalize_priority("") == "medium"


# =============================================================================
# GitHub Notification Processing Tests
# =============================================================================


class TestProcessGitHubNotifications:
    """Tests for GitHub notification → action item conversion."""

    def _create_user(self, db_session):
        user = User(
            email="github@example.com",
            password_hash=hash_password("TestPass123"),
        )
        db_session.add(user)
        db_session.flush()
        return user

    @pytest.mark.asyncio
    async def test_pr_review_creates_item(self, db_session):
        user = self._create_user(db_session)
        notifs = [{
            "source_id": "notif-1",
            "source_url": "https://github.com/org/repo/pull/1",
            "title": "Add login feature",
            "notification_type": "PullRequest",
            "reason": "review_requested",
            "action_type": "pr_review_requested",
            "repository": "org/repo",
            "updated_at": "2026-03-22T10:00:00Z",
            "unread": True,
        }]

        items = await process_github_notifications(
            notifs, user.id, db_session
        )
        assert len(items) == 1
        assert "Review PR" in items[0].title
        assert items[0].priority == "medium"
        assert items[0].confidence_score == 0.95

    @pytest.mark.asyncio
    async def test_ci_failure_high_priority(self, db_session):
        user = self._create_user(db_session)
        notifs = [{
            "source_id": "notif-2",
            "source_url": "https://github.com/org/repo/pull/2",
            "title": "CI failed",
            "action_type": "ci_failure",
            "repository": "org/repo",
        }]

        items = await process_github_notifications(
            notifs, user.id, db_session
        )
        assert len(items) == 1
        assert items[0].priority == "high"

    @pytest.mark.asyncio
    async def test_other_type_skipped(self, db_session):
        user = self._create_user(db_session)
        notifs = [{
            "source_id": "notif-3",
            "action_type": "other",
            "title": "Something",
        }]

        items = await process_github_notifications(
            notifs, user.id, db_session
        )
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_dedup_prevents_duplicate(self, db_session):
        user = self._create_user(db_session)
        notifs = [{
            "source_id": "notif-dup",
            "source_url": "https://github.com/org/repo/pull/1",
            "title": "Review this",
            "action_type": "pr_review_requested",
            "repository": "org/repo",
        }]

        # First call creates
        items1 = await process_github_notifications(
            notifs, user.id, db_session
        )
        assert len(items1) == 1

        # Second call deduplicates
        items2 = await process_github_notifications(
            notifs, user.id, db_session
        )
        assert len(items2) == 0


# =============================================================================
# Feedback Service Tests
# =============================================================================


class TestFeedbackService:
    """Tests for the feedback/dismissal service."""

    def _create_user_with_items(self, db_session):
        user = User(
            email="feedback@example.com",
            password_hash=hash_password("TestPass123"),
        )
        db_session.add(user)
        db_session.flush()

        items = []
        for i in range(3):
            item = ActionItem(
                user_id=user.id,
                source="gmail",
                title=f"Item {i}",
                priority="medium",
                status="new",
            )
            db_session.add(item)
            items.append(item)
        db_session.flush()
        return user, items

    def test_dismiss_action_item(self, db_session):
        user, items = self._create_user_with_items(db_session)
        result = dismiss_action_item(
            db_session,
            items[0].id,
            user.id,
            DismissReason.NOT_ACTION_ITEM,
        )
        assert result.status == "dismissed"
        assert result.dismiss_reason == "not_action_item"
        assert result.actioned_at is not None

    def test_dismiss_nonexistent_raises(self, db_session):
        user, _ = self._create_user_with_items(db_session)
        with pytest.raises(ValueError):
            dismiss_action_item(
                db_session,
                "nonexistent",
                user.id,
                DismissReason.ALREADY_DONE,
            )

    def test_dismissal_stats(self, db_session):
        user, items = self._create_user_with_items(db_session)

        # Dismiss two items
        dismiss_action_item(
            db_session,
            items[0].id,
            user.id,
            DismissReason.NOT_ACTION_ITEM,
        )
        dismiss_action_item(
            db_session,
            items[1].id,
            user.id,
            DismissReason.ALREADY_DONE,
        )

        stats = get_dismissal_stats(db_session, user.id)
        assert stats["total_items"] == 3
        assert stats["total_dismissed"] == 2
        assert abs(stats["dismissal_rate"] - 0.667) < 0.01
        assert stats["by_reason"]["not_action_item"] == 1
        assert stats["by_reason"]["already_done"] == 1
        assert stats["by_source"]["gmail"] == 2


# =============================================================================
# Action Items API Tests
# =============================================================================


class TestActionItemsAPI:
    """Tests for action items REST endpoints."""

    def _auth_headers(self, client):
        client.post("/api/v1/auth/register", json={
            "email": "actions@example.com",
            "password": "TestPass123",
        })
        resp = client.post("/api/v1/auth/login", json={
            "email": "actions@example.com",
            "password": "TestPass123",
        })
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_list_empty(self, client):
        headers = self._auth_headers(client)
        resp = client.get(
            "/api/v1/action-items", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_manual_item(self, client):
        headers = self._auth_headers(client)
        resp = client.post(
            "/api/v1/action-items",
            json={
                "title": "Follow up with Sarah",
                "description": "About the Q2 report",
                "priority": "high",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Follow up with Sarah"
        assert data["priority"] == "high"
        assert data["status"] == "new"
        assert data["source"] == "manual"

    def test_get_by_id(self, client):
        headers = self._auth_headers(client)
        create_resp = client.post(
            "/api/v1/action-items",
            json={"title": "Test item"},
            headers=headers,
        )
        item_id = create_resp.json()["id"]

        resp = client.get(
            f"/api/v1/action-items/{item_id}",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == item_id

    def test_get_nonexistent(self, client):
        headers = self._auth_headers(client)
        resp = client.get(
            "/api/v1/action-items/nonexistent",
            headers=headers,
        )
        assert resp.status_code == 404

    def test_dismiss_item(self, client):
        headers = self._auth_headers(client)
        create_resp = client.post(
            "/api/v1/action-items",
            json={"title": "Dismiss me"},
            headers=headers,
        )
        item_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/v1/action-items/{item_id}/dismiss",
            json={"reason": "not_action_item"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"
        assert resp.json()["dismiss_reason"] == "not_action_item"

    def test_acknowledge_item(self, client):
        headers = self._auth_headers(client)
        create_resp = client.post(
            "/api/v1/action-items",
            json={"title": "Acknowledge me"},
            headers=headers,
        )
        item_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/v1/action-items/{item_id}/acknowledge",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "acknowledged"

    def test_action_item_done(self, client):
        headers = self._auth_headers(client)
        create_resp = client.post(
            "/api/v1/action-items",
            json={"title": "Complete me"},
            headers=headers,
        )
        item_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/v1/action-items/{item_id}/action",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "actioned"
        assert resp.json()["actioned_at"] is not None

    def test_list_with_status_filter(self, client):
        headers = self._auth_headers(client)

        # Create two items
        client.post(
            "/api/v1/action-items",
            json={"title": "Item A"},
            headers=headers,
        )
        resp_b = client.post(
            "/api/v1/action-items",
            json={"title": "Item B"},
            headers=headers,
        )
        # Acknowledge item B
        item_b_id = resp_b.json()["id"]
        client.post(
            f"/api/v1/action-items/{item_b_id}/acknowledge",
            headers=headers,
        )

        # Filter by acknowledged
        resp = client.get(
            "/api/v1/action-items?status=acknowledged",
            headers=headers,
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["title"] == "Item B"

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/action-items")
        assert resp.status_code == 403
