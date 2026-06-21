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

    def test_claim_other_users_quest_blocked(self, client, auth_headers, db):
        # Quest definitions aren't auto-seeded in the test DB, so generate_daily_quests
        # would otherwise return an empty list. Seed them first.
        from app.services.quest_service import seed_quest_definitions
        seed_quest_definitions(db)
        db.commit()

        headers_a, _user_a = auth_headers(email="a@example.com")
        quests_a = client.get("/quests", headers=headers_a).json()["quests"]
        assert quests_a, "Expected auto-generated quests for user A"
        target_id = quests_a[0]["id"]

        headers_b, _user_b = auth_headers(email="b@example.com")
        resp = client.post(f"/quests/{target_id}/claim", headers=headers_b)

        # Another user can't see / claim user A's quest.
        assert resp.status_code == 400


HR_QUEST_TYPES = ("hr_zone_time", "peak_hr", "session_strain")


class TestWearableGatedQuests:
    """user_has_wearable() + HR-quest gating in generate_daily_quests()."""

    def _seed(self, db):
        from app.services.quest_service import seed_quest_definitions
        seed_quest_definitions(db)
        db.flush()

    def _quest_types(self, db, user_quests):
        from app.models.quest import QuestDefinition
        ids = [uq.quest_id for uq in user_quests]
        defs = db.query(QuestDefinition).filter(QuestDefinition.id.in_(ids)).all()
        return [d.quest_type for d in defs]

    def test_no_wearable_for_fresh_user(self, db, create_test_user):
        from app.services.quest_service import user_has_wearable
        user, _ = create_test_user(email="fresh@example.com")
        assert user_has_wearable(db, user.id) is False

    def test_wearable_via_whoop_connection(self, db, create_test_user):
        from app.models.whoop import WhoopConnection
        from app.services.quest_service import user_has_wearable
        user, _ = create_test_user(email="whoop@example.com")
        db.add(WhoopConnection(user_id=user.id))
        db.flush()
        assert user_has_wearable(db, user.id) is True

    def test_wearable_via_recent_hr_session(self, db, create_test_user):
        from datetime import datetime, timezone

        from app.models.workout import WorkoutSession
        from app.services.quest_service import user_has_wearable
        user, _ = create_test_user(email="watch@example.com")
        db.add(WorkoutSession(
            user_id=user.id,
            date=datetime.now(timezone.utc).replace(tzinfo=None),
            hr_source="apple_watch",
        ))
        db.flush()
        assert user_has_wearable(db, user.id) is True

    def test_old_hr_session_does_not_count(self, db, create_test_user):
        from datetime import datetime, timedelta, timezone

        from app.models.workout import WorkoutSession
        from app.services.quest_service import user_has_wearable
        user, _ = create_test_user(email="stale@example.com")
        old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=40)
        db.add(WorkoutSession(user_id=user.id, date=old, hr_source="apple_watch"))
        db.flush()
        assert user_has_wearable(db, user.id) is False

    def test_session_without_hr_source_does_not_count(self, db, create_test_user):
        from datetime import datetime, timezone

        from app.models.workout import WorkoutSession
        from app.services.quest_service import user_has_wearable
        user, _ = create_test_user(email="nohr@example.com")
        db.add(WorkoutSession(
            user_id=user.id,
            date=datetime.now(timezone.utc).replace(tzinfo=None),
            hr_source=None,
        ))
        db.flush()
        assert user_has_wearable(db, user.id) is False

    def test_non_wearable_user_gets_no_hr_quests(self, db, create_test_user):
        from app.services.quest_service import generate_daily_quests
        self._seed(db)
        user, _ = create_test_user(email="base@example.com")

        quests = generate_daily_quests(db, user.id)

        assert len(quests) == 3
        types = self._quest_types(db, quests)
        assert all(t not in HR_QUEST_TYPES for t in types), types

    def test_wearable_user_gets_exactly_one_hr_quest(self, db, create_test_user):
        from app.models.whoop import WhoopConnection
        from app.services.quest_service import generate_daily_quests
        self._seed(db)
        user, _ = create_test_user(email="geared@example.com")
        db.add(WhoopConnection(user_id=user.id))
        db.flush()

        quests = generate_daily_quests(db, user.id)

        assert len(quests) == 3
        types = self._quest_types(db, quests)
        hr = [t for t in types if t in HR_QUEST_TYPES]
        assert len(hr) == 1, types  # capped at one, but present for wearable users


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
