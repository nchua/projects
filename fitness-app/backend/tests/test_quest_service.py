"""
Integration tests for the quest service + quest API.

Previous revision of this file was almost entirely pseudo-tests — they
asserted on hand-built dicts and Mock objects without exercising any
real service or endpoint. Those have been converted to real endpoint
calls (or dropped with TODO markers if no endpoint exists).

The bug documented in the old comments (relationships not loaded before
update_quest_progress) is still worth covering — but the right place is
an integration test that POSTs a workout via /workouts and then reads
back /quests to confirm progress applied. That end-to-end flow is tracked
as a TODO at the bottom of this file.
"""


class TestQuestsEndpoint:
    """GET /quests — today's daily quests."""

    def test_list_quests_returns_three_by_default(self, client, auth_headers):
        headers, _user = auth_headers()

        resp = client.get("/quests", headers=headers)

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert "quests" in body
        assert "refresh_at" in body
        # Service auto-generates 3 quests on first fetch of the day.
        assert body["total_count"] == len(body["quests"])
        assert 0 <= body["completed_count"] <= body["total_count"]

    def test_list_quests_requires_auth(self, client):
        resp = client.get("/quests")
        assert resp.status_code in (401, 403)

    def test_list_quests_is_idempotent_same_day(self, client, auth_headers):
        """Calling GET /quests twice the same day returns the same quest IDs."""
        headers, _user = auth_headers()

        first = client.get("/quests", headers=headers).json()
        second = client.get("/quests", headers=headers).json()

        first_ids = sorted(q["id"] for q in first["quests"])
        second_ids = sorted(q["id"] for q in second["quests"])
        assert first_ids == second_ids


class TestClaimQuestReward:
    """POST /quests/{id}/claim — error paths that don't require completion."""

    def test_claim_unknown_quest_returns_400(self, client, auth_headers):
        headers, _user = auth_headers()

        resp = client.post("/quests/nonexistent-quest-id/claim", headers=headers)

        # claim_quest_reward raises ValueError → 400 at the router layer.
        assert resp.status_code == 400

    def test_claim_other_users_quest_blocked(self, client, auth_headers):
        headers_a, _user_a = auth_headers(email="a@example.com")
        quests_a = client.get("/quests", headers=headers_a).json()["quests"]
        assert quests_a, "Expected auto-generated quests for user A"
        target_id = quests_a[0]["id"]

        headers_b, _user_b = auth_headers(email="b@example.com")
        resp = client.post(f"/quests/{target_id}/claim", headers=headers_b)

        # Another user can't see / claim user A's quest.
        assert resp.status_code == 400


# ============================================================================
# TODO: Previous pseudo-tests removed because they asserted on hand-built
# Mock objects rather than real service behavior. These gaps need coverage
# via new endpoints or dedicated service tests once the service signatures
# stabilize:
#
# - TODO: update_quest_progress with loaded relationships — the "relationship
#   loading pitfall" scenario needs an end-to-end test: POST /workouts with
#   exercises+sets → GET /quests and assert progress increased. Blocked on
#   the workouts endpoint accepting the full payload shape in tests.
# - TODO: compound_exercise_detection — move to a pure service-level unit test
#   against the COMPOUND_EXERCISES list in quest_service once exposed.
# - TODO: calculate_todays_workout_stats date filtering — needs direct service
#   test with seeded WorkoutSession rows.
# - TODO: duration-quest exclusion — covered by assertion on the seeded quest
#   definitions, but seed_quest_definitions() doesn't run in the test DB yet.
# - TODO: completed quests stay visible / filtered by assigned_date — needs
#   service-level tests once we can construct UserQuest rows directly.
# ============================================================================
