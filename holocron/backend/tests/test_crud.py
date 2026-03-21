"""Tests for topics, concepts, and learning units CRUD."""


def test_topic_lifecycle(client, auth_headers):
    # Create
    resp = client.post(
        "/api/v1/topics",
        json={
            "name": "AI Tools",
            "description": "Applied AI",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    topic = resp.json()
    assert topic["name"] == "AI Tools"
    topic_id = topic["id"]

    # List
    resp = client.get("/api/v1/topics", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Get
    resp = client.get(f"/api/v1/topics/{topic_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "AI Tools"

    # Update
    resp = client.put(
        f"/api/v1/topics/{topic_id}",
        json={
            "name": "AI Tools & Frameworks",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "AI Tools & Frameworks"

    # Delete
    resp = client.delete(f"/api/v1/topics/{topic_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Verify gone
    resp = client.get(f"/api/v1/topics/{topic_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_concept_lifecycle(client, auth_headers):
    # Create topic first
    resp = client.post("/api/v1/topics", json={"name": "AI"}, headers=auth_headers)
    topic_id = resp.json()["id"]

    # Create concept
    resp = client.post(
        "/api/v1/concepts",
        json={
            "topic_id": topic_id,
            "name": "Chain of Thought",
            "description": "Step-by-step reasoning",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    concept = resp.json()
    assert concept["name"] == "Chain of Thought"
    assert concept["tier"] == "new"
    concept_id = concept["id"]

    # List by topic
    resp = client.get(f"/api/v1/concepts?topic_id={topic_id}", headers=auth_headers)
    assert len(resp.json()) == 1

    # Update
    resp = client.put(
        f"/api/v1/concepts/{concept_id}",
        json={
            "name": "CoT Prompting",
        },
        headers=auth_headers,
    )
    assert resp.json()["name"] == "CoT Prompting"

    # Delete
    resp = client.delete(f"/api/v1/concepts/{concept_id}", headers=auth_headers)
    assert resp.status_code == 204


def test_learning_unit_lifecycle(client, auth_headers):
    # Setup: topic + concept
    resp = client.post("/api/v1/topics", json={"name": "AI"}, headers=auth_headers)
    topic_id = resp.json()["id"]
    resp = client.post(
        "/api/v1/concepts",
        json={
            "topic_id": topic_id,
            "name": "RAG",
        },
        headers=auth_headers,
    )
    concept_id = resp.json()["id"]

    # Create card
    resp = client.post(
        "/api/v1/learning-units",
        json={
            "concept_id": concept_id,
            "type": "concept",
            "front_content": "What is RAG?",
            "back_content": (
                "Retrieval-Augmented Generation"
                " combines retrieval with generation."
            ),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    unit = resp.json()
    assert unit["front_content"] == "What is RAG?"
    assert unit["auto_accepted"] is True
    assert unit["next_review_at"] is not None
    unit_id = unit["id"]

    # Get due cards
    resp = client.get("/api/v1/learning-units/due", headers=auth_headers)
    assert resp.status_code == 200
    due = resp.json()
    assert len(due) == 1
    assert due[0]["topic_name"] == "AI"

    # Update content
    resp = client.put(
        f"/api/v1/learning-units/{unit_id}",
        json={
            "front_content": "What is RAG and what problem does it solve?",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Delete
    resp = client.delete(f"/api/v1/learning-units/{unit_id}", headers=auth_headers)
    assert resp.status_code == 204


def test_ai_card_inbox_routing(client, auth_headers):
    """AI-generated cards route through inbox based on confidence."""
    # Setup
    resp = client.post("/api/v1/topics", json={"name": "AI"}, headers=auth_headers)
    topic_id = resp.json()["id"]
    resp = client.post(
        "/api/v1/concepts",
        json={
            "topic_id": topic_id,
            "name": "Agents",
        },
        headers=auth_headers,
    )
    concept_id = resp.json()["id"]

    # High confidence → auto-accepted
    resp = client.post(
        "/api/v1/learning-units",
        json={
            "concept_id": concept_id,
            "front_content": "What are AI agents?",
            "back_content": "Autonomous systems that use LLMs to take actions.",
            "ai_generated": True,
            "confidence_score": 0.95,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["auto_accepted"] is True

    # Low confidence → pending inbox
    resp = client.post(
        "/api/v1/learning-units",
        json={
            "concept_id": concept_id,
            "front_content": "How do agents handle errors?",
            "back_content": "Through retry logic and fallback strategies.",
            "ai_generated": True,
            "confidence_score": 0.6,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["auto_accepted"] is False

    # Check inbox
    resp = client.get("/api/v1/inbox", headers=auth_headers)
    assert resp.status_code == 200
    inbox = resp.json()
    assert len(inbox) == 1
    assert inbox[0]["confidence_score"] == 0.6

    # Accept from inbox
    resp = client.put(
        f"/api/v1/inbox/{inbox[0]['id']}",
        json={
            "status": "accepted",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
