"""
Tests that achievement listing does not produce N+1 queries.

`get_recently_unlocked` iterates UserAchievement rows and reads
`ua.achievement.*`. Without a joinedload, each row triggers a separate
SELECT. This test hooks SQLAlchemy's `before_cursor_execute` event to
count SELECTs issued against the achievement_definitions table while the
endpoint runs, and asserts the count is at most 1 (the joined fetch).
"""
from datetime import datetime, timezone

from sqlalchemy import event

from app.core.database import engine
from app.models.achievement import AchievementDefinition, UserAchievement
from app.models.progress import UserProgress


def _seed_unlocked_achievements(db, user_id: str, count: int = 5):
    """Create `count` achievement definitions and unlock them for the user."""
    # User must have a UserProgress row (FK requirement on UserAchievement).
    progress = UserProgress(user_id=user_id, total_xp=0, level=1, rank="E")
    db.add(progress)
    db.flush()

    now = datetime.now(timezone.utc)
    for i in range(count):
        definition = AchievementDefinition(
            id=f"eager_test_ach_{i}",
            name=f"Eager Test {i}",
            description=f"description {i}",
            category="milestone",
            icon="star.fill",
            xp_reward=10,
            rarity="common",
            requirement_type="workout_count",
            requirement_value=i + 1,
            sort_order=i,
        )
        db.add(definition)
        db.flush()

        db.add(UserAchievement(
            user_id=user_id,
            user_progress_id=progress.id,
            achievement_id=definition.id,
            unlocked_at=now,
        ))

    db.commit()


class _SelectCounter:
    """Context manager that counts SELECTs hitting a given table."""

    def __init__(self, table_name: str):
        self.table_name = table_name
        self.count = 0
        self._listener = None

    def __enter__(self):
        def _on_execute(conn, cursor, statement, parameters, context, executemany):
            stmt_lower = statement.lower()
            if stmt_lower.lstrip().startswith("select") and self.table_name in stmt_lower:
                self.count += 1

        self._listener = _on_execute
        event.listen(engine, "before_cursor_execute", self._listener)
        return self

    def __exit__(self, exc_type, exc, tb):
        event.remove(engine, "before_cursor_execute", self._listener)
        return False


class TestAchievementEagerLoad:
    def test_recent_achievements_single_query(self, client, db, auth_headers):
        headers, user = auth_headers()
        _seed_unlocked_achievements(db, user.id, count=5)

        with _SelectCounter("achievement_definitions") as counter:
            resp = client.get("/progress/achievements/recent", headers=headers)

        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert len(payload["achievements"]) == 5

        # With joinedload, achievement_definitions should be fetched as part
        # of the UserAchievement SELECT (single statement) — not one extra
        # query per row.
        assert counter.count <= 1, (
            f"Expected <=1 select against achievement_definitions, got {counter.count}. "
            "joinedload(UserAchievement.achievement) appears to be missing."
        )
