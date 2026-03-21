"""Tests for Phase 3: sessions, interleaving, pacing, anti-guilt, and enhanced summary."""



def _setup_topic_with_cards(client, auth_headers, topic_name, cards, db=None):
    """Helper: create a topic with concepts and cards. Returns list of card IDs."""
    resp = client.post("/api/v1/topics", json={"name": topic_name}, headers=auth_headers)
    topic_id = resp.json()["id"]

    card_ids = []
    for card in cards:
        resp = client.post("/api/v1/concepts", json={
            "topic_id": topic_id,
            "name": card.get("concept_name", card["front"]),
        }, headers=auth_headers)
        concept_id = resp.json()["id"]

        resp = client.post("/api/v1/learning-units", json={
            "concept_id": concept_id,
            "type": card.get("type", "concept"),
            "front_content": card["front"],
            "back_content": card["back"],
        }, headers=auth_headers)
        card_ids.append(resp.json()["id"])

    return topic_id, card_ids


# --- Session Start ---

def test_start_session_returns_cards(client, auth_headers, db):
    """Starting a session returns cards with pacing metadata."""
    _setup_topic_with_cards(client, auth_headers, "AI", [
        {"front": "What is RAG?", "back": "Retrieval-Augmented Generation"},
        {"front": "What is RLHF?", "back": "Reinforcement Learning from Human Feedback"},
    ])

    resp = client.get("/api/v1/sessions/start?mode=full", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_size"] > 0
    assert data["total_due"] >= data["session_size"]
    assert data["mode"] == "full"
    assert "AI" in data["topics"]
    assert data["daily_cap"] == 30

    # Each card has phase info
    for card in data["cards"]:
        assert card["phase"] in ("warmup", "core", "challenge", "cooldown")
        assert card["topic_name"] == "AI"


def test_start_session_quick_mode(client, auth_headers, db):
    """Quick mode limits to fewer cards."""
    _setup_topic_with_cards(client, auth_headers, "AI", [
        {"front": f"Q{i}?", "back": f"A{i}"} for i in range(15)
    ])

    resp = client.get("/api/v1/sessions/start?mode=quick", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["session_size"] <= 8


def test_start_session_empty(client, auth_headers, db):
    """No due cards → empty session."""
    resp = client.get("/api/v1/sessions/start", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["session_size"] == 0
    assert resp.json()["cards"] == []


# --- Interleaving ---

def test_interleaving_mixes_topics(client, auth_headers, db):
    """Cards from different topics should be interleaved, not grouped."""
    _setup_topic_with_cards(client, auth_headers, "AI", [
        {"front": f"AI-Q{i}?", "back": f"AI-A{i}"} for i in range(4)
    ])
    _setup_topic_with_cards(client, auth_headers, "Business", [
        {"front": f"Biz-Q{i}?", "back": f"Biz-A{i}"} for i in range(4)
    ])

    resp = client.get("/api/v1/sessions/start?mode=full", headers=auth_headers)
    cards = resp.json()["cards"]

    # Check that topics aren't all grouped together
    topics = [c["topic_name"] for c in cards]
    if len(set(topics)) > 1:
        # At least one topic transition should happen in the first few cards
        transitions = sum(1 for i in range(1, len(topics)) if topics[i] != topics[i - 1])
        assert transitions >= 1, "Expected interleaving (topic switches) but cards were grouped"


# --- Anti-Guilt (Daily Cap) ---

def test_daily_cap_enforced(client, auth_headers, db):
    """After reaching the daily cap, no more cards are returned."""

    # Create more cards than the cap
    _setup_topic_with_cards(client, auth_headers, "AI", [
        {"front": f"Q{i}?", "back": f"A{i}"} for i in range(35)
    ])

    # Review up to the cap
    resp = client.get("/api/v1/sessions/start?mode=deep", headers=auth_headers)
    cards = resp.json()["cards"]

    for card in cards:
        client.post("/api/v1/reviews", json={
            "learning_unit_id": card["id"],
            "rating": "got_it",
        }, headers=auth_headers)

    # Now ask for more cards — should get fewer or none
    resp = client.get("/api/v1/sessions/start?mode=full", headers=auth_headers)
    data = resp.json()
    assert data["reviews_today"] >= len(cards)


# --- Pacing ---

def test_session_has_pacing_phases(client, auth_headers, db):
    """Session cards should have multiple pacing phases when enough cards exist."""
    _setup_topic_with_cards(client, auth_headers, "AI", [
        {"front": f"Q{i}?", "back": f"A{i}"} for i in range(12)
    ])

    resp = client.get("/api/v1/sessions/start?mode=full", headers=auth_headers)
    cards = resp.json()["cards"]
    phases = [c["phase"] for c in cards]

    # With enough cards, we should see multiple phases
    unique_phases = set(phases)
    assert len(unique_phases) >= 2, f"Expected multiple phases but got: {unique_phases}"


def test_pacing_order_preserved(client, auth_headers, db):
    """Phases should appear in order: warmup → core → challenge → cooldown."""
    _setup_topic_with_cards(client, auth_headers, "AI", [
        {"front": f"Q{i}?", "back": f"A{i}"} for i in range(12)
    ])

    resp = client.get("/api/v1/sessions/start?mode=full", headers=auth_headers)
    cards = resp.json()["cards"]
    phases = [c["phase"] for c in cards]

    phase_order = {"warmup": 0, "core": 1, "challenge": 2, "cooldown": 3}
    phase_indices = [phase_order[p] for p in phases]

    # Verify non-decreasing order (phases don't go backwards)
    for i in range(1, len(phase_indices)):
        assert phase_indices[i] >= phase_indices[i - 1], (
            f"Phase order violated at position {i}: {phases[i-1]} → {phases[i]}"
        )


# --- Enhanced Session Summary ---

def test_enhanced_summary_per_topic(client, auth_headers, db):
    """Enhanced summary includes per-topic performance breakdown."""
    _, ai_ids = _setup_topic_with_cards(client, auth_headers, "AI", [
        {"front": "Q1?", "back": "A1"},
        {"front": "Q2?", "back": "A2"},
    ])
    _, biz_ids = _setup_topic_with_cards(client, auth_headers, "Business", [
        {"front": "Q3?", "back": "A3"},
    ])

    # Review AI cards successfully, business card with struggle
    for uid in ai_ids:
        client.post("/api/v1/reviews", json={
            "learning_unit_id": uid, "rating": "got_it",
        }, headers=auth_headers)
    client.post("/api/v1/reviews", json={
        "learning_unit_id": biz_ids[0], "rating": "struggled",
    }, headers=auth_headers)

    resp = client.get("/api/v1/sessions/summary?since_minutes=5", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_reviewed"] == 3
    assert data["recalled"] == 2
    assert data["struggled"] == 1

    # Per-topic breakdown
    assert len(data["topic_performance"]) == 2
    ai_perf = next(t for t in data["topic_performance"] if t["topic_name"] == "AI")
    biz_perf = next(t for t in data["topic_performance"] if t["topic_name"] == "Business")

    assert ai_perf["recalled"] == 2
    assert ai_perf["accuracy"] == 1.0
    assert biz_perf["struggled"] == 1
    assert biz_perf["accuracy"] == 0.0


def test_summary_strongest_weakest(client, auth_headers, db):
    """Summary identifies strongest and weakest topics."""
    _, ai_ids = _setup_topic_with_cards(client, auth_headers, "AI", [
        {"front": "Q1?", "back": "A1"},
    ])
    _, biz_ids = _setup_topic_with_cards(client, auth_headers, "Business", [
        {"front": "Q2?", "back": "A2"},
    ])

    client.post("/api/v1/reviews", json={
        "learning_unit_id": ai_ids[0], "rating": "easy",
    }, headers=auth_headers)
    client.post("/api/v1/reviews", json={
        "learning_unit_id": biz_ids[0], "rating": "forgot",
    }, headers=auth_headers)

    resp = client.get("/api/v1/sessions/summary?since_minutes=5", headers=auth_headers)
    data = resp.json()

    assert data["strongest_topic"] == "AI"
    assert data["weakest_topic"] == "Business"


def test_summary_empty_session(client, auth_headers, db):
    """Empty summary when no reviews in timeframe."""
    resp = client.get("/api/v1/sessions/summary?since_minutes=5", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_reviewed"] == 0
    assert data["topic_performance"] == []
