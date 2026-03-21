"""Tests for review submission and FSRS integration."""


def _setup_card(client, auth_headers):
    """Helper: create topic → concept → card, return card id."""
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
    resp = client.post(
        "/api/v1/learning-units",
        json={
            "concept_id": concept_id,
            "front_content": "What is RAG?",
            "back_content": "Retrieval-Augmented Generation.",
        },
        headers=auth_headers,
    )
    return resp.json()["id"]


def test_submit_review(client, auth_headers):
    unit_id = _setup_card(client, auth_headers)

    resp = client.post(
        "/api/v1/reviews",
        json={
            "learning_unit_id": unit_id,
            "rating": "got_it",
            "time_to_reveal_ms": 2500,
            "time_reading_ms": 4000,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    review = resp.json()
    assert review["rating"] == "got_it"
    assert review["next_review_at"] is not None

    # Verify card was updated
    resp = client.get(f"/api/v1/learning-units/{unit_id}", headers=auth_headers)
    unit = resp.json()
    assert unit["review_count"] == 1
    assert unit["stability"] > 0


def test_review_forgot_increments_lapse(client, auth_headers):
    unit_id = _setup_card(client, auth_headers)

    resp = client.post(
        "/api/v1/reviews",
        json={
            "learning_unit_id": unit_id,
            "rating": "forgot",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201

    resp = client.get(f"/api/v1/learning-units/{unit_id}", headers=auth_headers)
    assert resp.json()["lapse_count"] == 1


def test_review_history(client, auth_headers):
    unit_id = _setup_card(client, auth_headers)

    # Submit two reviews
    for rating in ["got_it", "easy"]:
        client.post(
            "/api/v1/reviews",
            json={
                "learning_unit_id": unit_id,
                "rating": rating,
            },
            headers=auth_headers,
        )

    resp = client.get("/api/v1/reviews/history", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_session_summary(client, auth_headers):
    unit_id = _setup_card(client, auth_headers)

    client.post(
        "/api/v1/reviews",
        json={
            "learning_unit_id": unit_id,
            "rating": "got_it",
        },
        headers=auth_headers,
    )

    resp = client.get("/api/v1/reviews/summary?since_minutes=5", headers=auth_headers)
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total_reviewed"] == 1
    assert summary["recalled"] == 1
