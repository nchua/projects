"""Tests for memory, triage rules, and prioritization services."""

from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.models.action_item import ActionItem
from app.models.contact import ActionItemContact, Contact
from app.models.enums import ActionItemStatus, DismissReason
from app.models.memory_fact import MemoryFact
from app.models.user import User
from app.services.feedback_service import dismiss_action_item
from app.services.memory_service import (
    _fact_dedup_hash,
    _texts_match,
    get_relevant_memories,
    persist_memory_facts,
)
from app.services.prioritization_service import (
    _compute_deadline_urgency,
    compute_contact_importance,
    rerank_action_items,
    score_action_item,
)
from app.services.triage_rules import (
    COLD_START_THRESHOLD,
    DEFAULT_CONFIDENCE_THRESHOLD,
    compute_triage_config,
    get_source_threshold,
    should_suppress_sender,
)


# =============================================================================
# Helpers
# =============================================================================


def _create_user(db_session, email="test@example.com"):
    user = User(
        email=email,
        password_hash=hash_password("TestPass123"),
    )
    db_session.add(user)
    db_session.flush()
    return user


def _create_action_item(db_session, user_id, **kwargs):
    defaults = {
        "source": "gmail",
        "title": "Test item",
        "priority": "medium",
        "status": ActionItemStatus.NEW.value,
    }
    defaults.update(kwargs)
    item = ActionItem(user_id=user_id, **defaults)
    db_session.add(item)
    db_session.flush()
    return item


# =============================================================================
# Triage Rules
# =============================================================================


class TestTriageRules:
    """Tests for adaptive triage rules."""

    def test_default_threshold_no_config(self, db_session):
        """New user with no triage config gets default threshold."""
        user = _create_user(db_session)
        threshold = get_source_threshold(user.id, "gmail", db_session)
        assert threshold == DEFAULT_CONFIDENCE_THRESHOLD

    def test_threshold_from_config(self, db_session):
        """User with triage config gets custom threshold."""
        user = _create_user(db_session)
        user.triage_config = {"source_thresholds": {"gmail": 0.85}}
        db_session.flush()

        threshold = get_source_threshold(user.id, "gmail", db_session)
        assert threshold == 0.85

    def test_cold_start_no_adaptation(self, db_session):
        """Sources with < COLD_START_THRESHOLD dismissals don't adapt."""
        user = _create_user(db_session)

        # Create 10 dismissed items (below threshold of 20)
        for i in range(10):
            _create_action_item(
                db_session,
                user.id,
                title=f"Item {i}",
                source="gmail",
                status=ActionItemStatus.DISMISSED.value,
                dedup_hash=f"hash-{i}",
            )

        config = compute_triage_config(user.id, db_session)
        assert config["source_thresholds"] == {}

    def test_high_dismissal_raises_threshold(self, db_session):
        """Sources with >70% dismissal rate get 0.85 threshold."""
        user = _create_user(db_session, email="triage@example.com")

        # Create 30 items: 25 dismissed, 5 not
        for i in range(25):
            _create_action_item(
                db_session,
                user.id,
                title=f"Dismissed {i}",
                source="gmail",
                status=ActionItemStatus.DISMISSED.value,
                dedup_hash=f"d-{i}",
            )
        for i in range(5):
            _create_action_item(
                db_session,
                user.id,
                title=f"New {i}",
                source="gmail",
                status=ActionItemStatus.NEW.value,
                dedup_hash=f"n-{i}",
            )

        config = compute_triage_config(user.id, db_session)
        # 25/30 = 83% > 70% → threshold = 0.85
        assert config["source_thresholds"]["gmail"] == 0.85

    def test_should_suppress_sender_false_no_config(self, db_session):
        """No suppression without triage config."""
        user = _create_user(db_session, email="sup@example.com")
        assert not should_suppress_sender(
            user.id, "alice@example.com", db_session
        )

    def test_should_suppress_sender_true(self, db_session):
        """Sender in suppressed list is suppressed."""
        user = _create_user(db_session, email="sup2@example.com")
        user.triage_config = {
            "suppressed_senders": ["spam@example.com"],
        }
        db_session.flush()

        assert should_suppress_sender(
            user.id, "spam@example.com", db_session
        )
        assert not should_suppress_sender(
            user.id, "good@example.com", db_session
        )


# =============================================================================
# Memory Service
# =============================================================================


class TestMemoryService:
    """Tests for memory fact persistence and retrieval."""

    def test_persist_new_fact(self, db_session):
        """New facts are created with is_active=True."""
        user = _create_user(db_session, email="mem@example.com")

        facts = persist_memory_facts(
            [
                {
                    "fact_text": "Alice committed to delivering spec by Friday",
                    "fact_type": "commitment",
                    "people": ["alice@example.com"],
                    "valid_from": "2026-03-22",
                    "valid_until": "2026-03-27",
                    "importance": 0.8,
                    "confidence": 0.9,
                }
            ],
            user.id,
            db_session,
        )

        assert len(facts) == 1
        assert facts[0].is_active is True
        assert facts[0].fact_type == "commitment"
        assert facts[0].importance == 0.8

    def test_persist_duplicate_fact_noop(self, db_session):
        """Identical facts are treated as NOOP (not duplicated)."""
        user = _create_user(db_session, email="mem2@example.com")

        fact_data = {
            "fact_text": "Q2 budget review is next Tuesday",
            "fact_type": "deadline",
            "people": [],
            "importance": 0.7,
        }

        facts1 = persist_memory_facts([fact_data], user.id, db_session)
        facts2 = persist_memory_facts([fact_data], user.id, db_session)

        assert len(facts1) == 1
        assert len(facts2) == 0  # NOOP

    def test_persist_update_supersedes_old(self, db_session):
        """Updated facts supersede old ones via superseded_by_id."""
        user = _create_user(db_session, email="mem3@example.com")

        old = persist_memory_facts(
            [
                {
                    "fact_text": "Spec deadline is Friday",
                    "fact_type": "deadline",
                    "people": ["alice"],
                    "importance": 0.8,
                }
            ],
            user.id,
            db_session,
        )
        assert len(old) == 1
        old_id = old[0].id

        # Update with different text but same dedup hash (same people pattern)
        new = persist_memory_facts(
            [
                {
                    "fact_text": "Spec deadline moved to next Monday",
                    "fact_type": "deadline",
                    "people": ["alice"],
                    "importance": 0.9,
                }
            ],
            user.id,
            db_session,
        )
        assert len(new) == 1

        db_session.refresh(old[0])
        assert old[0].is_active is False
        assert old[0].invalidated_at is not None
        assert old[0].superseded_by_id == new[0].id

    def test_get_relevant_memories(self, db_session):
        """Retrieves active facts relevant to target date."""
        user = _create_user(db_session, email="mem4@example.com")
        now = datetime.now(tz=timezone.utc)

        # Active fact valid today
        fact1 = MemoryFact(
            user_id=user.id,
            fact_text="Team standup moved to 10am",
            fact_type="context",
            source="slack",
            valid_from=now - timedelta(days=1),
            importance=0.6,
            is_active=True,
        )
        # Inactive fact (should not appear)
        fact2 = MemoryFact(
            user_id=user.id,
            fact_text="Old fact",
            fact_type="context",
            source="gmail",
            valid_from=now - timedelta(days=5),
            importance=0.5,
            is_active=False,
        )
        # Future fact (should not appear)
        fact3 = MemoryFact(
            user_id=user.id,
            fact_text="Future fact",
            fact_type="context",
            source="gmail",
            valid_from=now + timedelta(days=10),
            importance=0.5,
            is_active=True,
        )
        db_session.add_all([fact1, fact2, fact3])
        db_session.flush()

        results = get_relevant_memories(
            user.id, now.date(), db_session
        )

        assert len(results) == 1
        assert results[0].id == fact1.id
        assert results[0].access_count == 1

    def test_dedup_hash_deterministic(self):
        """Same text + people produce same hash."""
        h1 = _fact_dedup_hash("test fact", ["alice"])
        h2 = _fact_dedup_hash("test fact", ["alice"])
        assert h1 == h2

    def test_dedup_hash_differs_on_text(self):
        """Different text produces different hash."""
        h1 = _fact_dedup_hash("fact A", [])
        h2 = _fact_dedup_hash("fact B", [])
        assert h1 != h2

    def test_texts_match_exact(self):
        assert _texts_match("hello world", "hello world") is True

    def test_texts_match_prefix(self):
        assert _texts_match("hello", "hello world") is True

    def test_texts_no_match(self):
        assert _texts_match("hello", "goodbye") is False


# =============================================================================
# Prioritization
# =============================================================================


class TestPrioritization:
    """Tests for RFM-based prioritization."""

    def test_compute_contact_importance_high_frequency(self, db_session):
        """Frequent contacts with recent interactions score high."""
        user = _create_user(db_session, email="pri@example.com")
        contact = Contact(
            user_id=user.id,
            display_name="Alice",
            email="alice@example.com",
            interaction_count=30,
            action_item_count=30,
            dismissal_count=0,
            last_interaction_at=datetime.now(tz=timezone.utc),
        )
        db_session.add(contact)
        db_session.flush()

        score = compute_contact_importance(contact)
        assert score > 0.3  # Baseline for active contact

    def test_compute_contact_importance_stale(self, db_session):
        """Contacts with no recent interactions score lower."""
        user = _create_user(db_session, email="pri2@example.com")
        contact = Contact(
            user_id=user.id,
            display_name="Bob",
            email="bob@example.com",
            interaction_count=5,
            action_item_count=5,
            dismissal_count=0,
            last_interaction_at=datetime.now(tz=timezone.utc)
            - timedelta(days=90),
        )
        db_session.add(contact)
        db_session.flush()

        score = compute_contact_importance(contact)
        assert score < 0.2  # Low due to recency decay

    def test_compute_contact_importance_high_dismissal(self, db_session):
        """Contacts with high dismissal rate get penalty."""
        user = _create_user(db_session, email="pri3@example.com")
        contact = Contact(
            user_id=user.id,
            display_name="Spam Bot",
            email="spam@example.com",
            interaction_count=50,
            action_item_count=50,
            dismissal_count=40,
            last_interaction_at=datetime.now(tz=timezone.utc),
        )
        db_session.add(contact)
        db_session.flush()

        score = compute_contact_importance(contact)
        # With 80% dismissal rate, penalty = 1.0 - 0.8*0.5 = 0.6
        assert score < 0.4

    def test_deadline_urgency_past_due(self):
        """Past-due deadlines have max urgency."""
        past = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        assert _compute_deadline_urgency(past) == 1.0

    def test_deadline_urgency_tomorrow(self):
        """Deadlines within 24h have max urgency."""
        tomorrow = datetime.now(tz=timezone.utc) + timedelta(hours=12)
        assert _compute_deadline_urgency(tomorrow) == 1.0

    def test_deadline_urgency_next_week(self):
        """Deadlines 3 days away have moderate urgency."""
        future = datetime.now(tz=timezone.utc) + timedelta(days=3)
        assert _compute_deadline_urgency(future) == 0.4

    def test_deadline_urgency_none(self):
        """No deadline = no urgency."""
        assert _compute_deadline_urgency(None) == 0.0

    def test_score_action_item(self, db_session):
        """Composite score uses all weight components."""
        user = _create_user(db_session, email="score@example.com")
        item = _create_action_item(
            db_session,
            user.id,
            priority="high",
            confidence_score=0.9,
        )

        score = score_action_item(
            item, contact_score=0.8, source_dismissal_rate=0.1
        )
        # All components contribute positively
        assert 0.5 < score < 1.0

    def test_rerank_action_items(self, db_session):
        """Reranking orders by composite score."""
        user = _create_user(db_session, email="rerank@example.com")

        high = _create_action_item(
            db_session,
            user.id,
            title="High priority",
            priority="high",
            confidence_score=0.95,
            dedup_hash="rr-high",
        )
        low = _create_action_item(
            db_session,
            user.id,
            title="Low priority",
            priority="low",
            confidence_score=0.3,
            dedup_hash="rr-low",
        )

        ranked = rerank_action_items(
            [low, high], user.id, db_session
        )

        assert ranked[0].id == high.id
        assert ranked[1].id == low.id


# =============================================================================
# Feedback Service Integration
# =============================================================================


class TestFeedbackIntegration:
    """Tests for dismiss → contact stats → triage config pipeline."""

    def test_dismiss_updates_contact_stats(self, db_session):
        """Dismissing an item increments contact dismissal_count."""
        user = _create_user(db_session, email="fb@example.com")

        contact = Contact(
            user_id=user.id,
            display_name="Test Contact",
            email="contact@example.com",
            interaction_count=5,
            action_item_count=5,
            dismissal_count=0,
        )
        db_session.add(contact)
        db_session.flush()

        item = _create_action_item(
            db_session, user.id, dedup_hash="fb-1"
        )

        # Link item to contact
        link = ActionItemContact(
            action_item_id=item.id,
            contact_id=contact.id,
        )
        db_session.add(link)
        db_session.flush()

        dismiss_action_item(
            db_session, item.id, user.id,
            DismissReason.NOT_ACTION_ITEM,
        )

        db_session.refresh(contact)
        assert contact.dismissal_count == 1

    def test_dismiss_computes_time_to_action(self, db_session):
        """Dismissal sets time_to_action_secs on the item."""
        user = _create_user(db_session, email="fb2@example.com")
        item = _create_action_item(
            db_session, user.id, dedup_hash="fb-2"
        )

        dismiss_action_item(
            db_session, item.id, user.id,
            DismissReason.ALREADY_DONE,
        )

        db_session.refresh(item)
        assert item.time_to_action_secs is not None
        assert item.time_to_action_secs >= 0


# =============================================================================
# Memory API Endpoints
# =============================================================================


class TestMemoryAPI:
    """Tests for the memory REST API."""

    def _register_and_login(self, client):
        client.post("/api/v1/auth/register", json={
            "email": "memapi@example.com",
            "password": "TestPass123",
        })
        response = client.post("/api/v1/auth/login", json={
            "email": "memapi@example.com",
            "password": "TestPass123",
        })
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_list_memory_facts_empty(self, client):
        """GET /api/v1/memory returns empty list for new user."""
        headers = self._register_and_login(client)
        response = client.get("/api/v1/memory", headers=headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_create_memory_fact(self, client):
        """POST /api/v1/memory creates a fact."""
        headers = self._register_and_login(client)
        response = client.post(
            "/api/v1/memory",
            json={
                "fact_text": "Q3 planning is July 15",
                "fact_type": "deadline",
                "importance": 0.9,
            },
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["fact_text"] == "Q3 planning is July 15"
        assert data["fact_type"] == "deadline"
        assert data["is_active"] is True
        assert data["source"] == "manual"

    def test_delete_memory_fact(self, client):
        """DELETE /api/v1/memory/{id} soft-deletes a fact."""
        headers = self._register_and_login(client)

        # Create
        create_resp = client.post(
            "/api/v1/memory",
            json={"fact_text": "To be deleted", "fact_type": "context"},
            headers=headers,
        )
        fact_id = create_resp.json()["id"]

        # Delete
        del_resp = client.delete(
            f"/api/v1/memory/{fact_id}", headers=headers
        )
        assert del_resp.status_code == 204

        # Verify not in active list
        list_resp = client.get("/api/v1/memory", headers=headers)
        ids = [f["id"] for f in list_resp.json()]
        assert fact_id not in ids

    def test_delete_nonexistent_returns_404(self, client):
        """DELETE /api/v1/memory/{bad_id} returns 404."""
        headers = self._register_and_login(client)
        response = client.delete(
            "/api/v1/memory/nonexistent", headers=headers
        )
        assert response.status_code == 404

    def test_memory_requires_auth(self, client):
        """Memory endpoints require authentication."""
        response = client.get("/api/v1/memory")
        assert response.status_code == 403
