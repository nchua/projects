"""
Tests for the WHOOP integration (Phase 1 wearable HR).

Covers the pure logic (token encryption, OAuth state, zone mapping, session
time-overlap matching, summary backfill) and an end-to-end sync that monkeypatches
the WHOOP HTTP layer and asserts session HR backfills on sync.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.crypto import decrypt_token, encrypt_token
from app.models.exercise import Exercise
from app.models.whoop import WhoopConnection
from app.models.workout import Set, WeightUnit, WorkoutExercise, WorkoutSession
from app.services import whoop_service

# ── Pure-logic unit tests ─────────────────────────────────────────────────────

class TestTokenEncryption:
    def test_round_trip(self):
        token = "whoop-access-token-abc123"
        ciphertext = encrypt_token(token)
        assert ciphertext != token  # actually encrypted
        assert decrypt_token(ciphertext) == token

    def test_none_and_empty(self):
        assert encrypt_token(None) is None
        assert encrypt_token("") is None
        assert decrypt_token(None) is None
        assert decrypt_token("not-valid-ciphertext") is None

    def test_model_properties_encrypt_at_rest(self):
        conn = WhoopConnection(user_id="u1")
        conn.access_token = "plain-access"
        conn.refresh_token = "plain-refresh"
        # Stored columns hold ciphertext, not plaintext.
        assert conn.access_token_encrypted not in (None, "plain-access")
        assert "plain-access" not in conn.access_token_encrypted
        # Properties decrypt transparently.
        assert conn.access_token == "plain-access"
        assert conn.refresh_token == "plain-refresh"


class TestOAuthState:
    def test_state_round_trip(self):
        state = whoop_service.generate_oauth_state("user-42")
        assert whoop_service.verify_oauth_state(state) == "user-42"

    def test_invalid_state_rejected(self):
        assert whoop_service.verify_oauth_state("garbage") is None
        assert whoop_service.verify_oauth_state("") is None


class TestZoneMapping:
    def test_v1_zone_duration_milli_to_seconds(self):
        score = {
            "zone_duration": {
                "zone_zero_milli": 13458,
                "zone_one_milli": 389370,
                "zone_two_milli": 388275,
                "zone_three_milli": 71091,
                "zone_four_milli": 0,
                "zone_five_milli": 0,
            }
        }
        zones = whoop_service._zone_seconds_from_whoop(score)
        assert zones["z1"] == 389  # 389370 / 1000 rounded
        assert zones["z2"] == 388
        assert zones["z3"] == 71
        assert zones["z4"] == 0
        assert zones["z5"] == 0

    def test_v2_zone_durations_plural_supported(self):
        score = {"zone_durations": {"zone_two_milli": 600000}}
        zones = whoop_service._zone_seconds_from_whoop(score)
        assert zones["z2"] == 600

    def test_missing_zones(self):
        assert whoop_service._zone_seconds_from_whoop({}) == {}


class TestSessionMatching:
    def _session(self, start, duration=60):
        s = WorkoutSession(id=str(uuid.uuid4()), user_id="u1", date=start)
        s.duration_minutes = duration
        return s

    def test_overlapping_session_matches(self):
        # WHOOP workout 10:00-10:45; session 10:05-11:05 -> overlap.
        whoop_start = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
        whoop_end = datetime(2026, 6, 1, 10, 45, tzinfo=timezone.utc)
        session = self._session(datetime(2026, 6, 1, 10, 5), duration=60)
        assert whoop_service._find_matching_session([session], whoop_start, whoop_end) is session

    def test_non_overlapping_session_does_not_match(self):
        whoop_start = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
        whoop_end = datetime(2026, 6, 1, 10, 45, tzinfo=timezone.utc)
        session = self._session(datetime(2026, 6, 1, 14, 0), duration=60)
        assert whoop_service._find_matching_session([session], whoop_start, whoop_end) is None

    def test_date_only_session_spans_whole_day(self):
        # Session logged at local midnight (date-only) should match a same-day
        # afternoon WHOOP workout.
        whoop_start = datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc)
        whoop_end = datetime(2026, 6, 1, 15, 40, tzinfo=timezone.utc)
        session = self._session(datetime(2026, 6, 1, 0, 0), duration=None)
        assert whoop_service._find_matching_session([session], whoop_start, whoop_end) is session

    def test_best_overlap_wins(self):
        whoop_start = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
        whoop_end = datetime(2026, 6, 1, 11, 0, tzinfo=timezone.utc)
        small = self._session(datetime(2026, 6, 1, 10, 50), duration=30)   # 10m overlap
        big = self._session(datetime(2026, 6, 1, 10, 10), duration=60)     # 50m overlap
        assert whoop_service._find_matching_session([small, big], whoop_start, whoop_end) is big


class TestApplySummary:
    def test_backfills_empty_fields(self):
        session = WorkoutSession(id="s1", user_id="u1", date=datetime(2026, 6, 1, 10, 0))
        score = {
            "strain": 14.3,
            "average_heart_rate": 132,
            "max_heart_rate": 168,
            "kilojoule": 1569.3,
            "zone_duration": {"zone_two_milli": 600000, "zone_three_milli": 300000},
        }
        changed = whoop_service.apply_whoop_summary(session, score)
        assert changed is True
        assert session.avg_heart_rate == 132
        assert session.peak_heart_rate == 168
        assert session.strain == pytest.approx(14.3)
        assert session.kilojoules == pytest.approx(1569.3)
        assert session.hr_zone_seconds == {"z2": 600, "z3": 300}
        assert session.hr_source == "whoop"

    def test_non_destructive_does_not_clobber_apple_watch(self):
        session = WorkoutSession(id="s1", user_id="u1", date=datetime(2026, 6, 1, 10, 0))
        session.avg_heart_rate = 140
        session.hr_source = "apple_watch"
        score = {"average_heart_rate": 132, "strain": 12.0}
        changed = whoop_service.apply_whoop_summary(session, score)
        # avg stays from the watch; only the empty strain field fills in.
        assert session.avg_heart_rate == 140
        assert session.hr_source == "apple_watch"
        assert session.strain == pytest.approx(12.0)
        assert changed is True


# ── End-to-end sync (real DB, monkeypatched WHOOP HTTP) ──────────────────────

class TestSyncEndToEnd:
    def _seed_session_with_set(self, db, user_id, when):
        exercise = Exercise(id=str(uuid.uuid4()), name="Barbell Back Squat", category="compound")
        db.add(exercise)
        session = WorkoutSession(id=str(uuid.uuid4()), user_id=user_id, date=when, duration_minutes=60)
        db.add(session)
        we = WorkoutExercise(id=str(uuid.uuid4()), session_id=session.id, exercise_id=exercise.id, order_index=0)
        db.add(we)
        db.add(Set(id=str(uuid.uuid4()), workout_exercise_id=we.id, weight=225, weight_unit=WeightUnit.LB, reps=5, set_number=1))
        db.commit()
        return session

    def test_sync_backfills_hr(self, db, create_test_user, monkeypatch):
        user, _ = create_test_user(email=f"whoop-{uuid.uuid4().hex[:8]}@example.com")

        # A workout logged today (UTC) at 10:00.
        today = datetime.now(timezone.utc).date()
        session_start = datetime(today.year, today.month, today.day, 10, 0)
        session = self._seed_session_with_set(db, user.id, session_start)

        # A connected WHOOP account.
        conn = WhoopConnection(user_id=user.id)
        conn.access_token = "access"
        conn.refresh_token = "refresh"
        conn.expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
        conn.scope = "offline read:profile read:workout"
        db.add(conn)

        db.commit()

        # Monkeypatch the WHOOP HTTP layer: configured + a scored workout overlapping the session.
        monkeypatch.setattr(whoop_service, "is_configured", lambda: True)
        monkeypatch.setattr(whoop_service, "_require_configured", lambda: None)
        whoop_workout = {
            "id": "w1",
            "score_state": "SCORED",
            "start": session_start.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "end": (session_start + timedelta(minutes=45)).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "score": {
                "strain": 15.4,
                "average_heart_rate": 138,
                "max_heart_rate": 172,
                "kilojoule": 1700.0,
                "zone_duration": {"zone_two_milli": 1200000, "zone_three_milli": 600000},
            },
        }
        monkeypatch.setattr(whoop_service, "fetch_recent_workouts", lambda *a, **k: [whoop_workout])

        result = whoop_service.sync_recent_workouts(db, user.id)

        # Session HR backfilled.
        db.refresh(session)
        assert session.avg_heart_rate == 138
        assert session.peak_heart_rate == 172
        assert session.strain == pytest.approx(15.4)
        assert session.hr_zone_seconds == {"z2": 1200, "z3": 600}
        assert session.hr_source == "whoop"

        assert result["sessions_matched"] == 1
        assert result["sessions_updated"] == 1

        # Daily quests were removed in Phase 0; the key stays, always empty.
        assert result["quests_completed"] == []

    def test_sync_without_connection_raises(self, db, create_test_user):
        user, _ = create_test_user(email=f"noconn-{uuid.uuid4().hex[:8]}@example.com")
        with pytest.raises(whoop_service.WhoopNotConnected):
            whoop_service.sync_recent_workouts(db, user.id)


# ── API surface ───────────────────────────────────────────────────────────────

class TestWhoopApi:
    def test_status_not_connected(self, client, auth_headers):
        headers, _ = auth_headers(email=f"status-{uuid.uuid4().hex[:8]}@example.com")
        resp = client.get("/whoop/status", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_status_requires_auth(self, client):
        assert client.get("/whoop/status").status_code in (401, 403)

    def test_connect_returns_503_when_unconfigured(self, client, auth_headers, monkeypatch):
        # No WHOOP credentials in the test env -> connect should 503.
        headers, _ = auth_headers(email=f"connect-{uuid.uuid4().hex[:8]}@example.com")
        resp = client.get("/whoop/connect", headers=headers)
        assert resp.status_code == 503

    def test_connect_returns_url_when_configured(self, client, auth_headers, monkeypatch):
        # Patch the exact settings object whoop_service reads. (Patching
        # app.core.config.settings can desync if another test reloads that
        # module — test_config_guard does — leaving a different singleton.)
        settings = whoop_service.settings
        monkeypatch.setattr(settings, "WHOOP_CLIENT_ID", "cid")
        monkeypatch.setattr(settings, "WHOOP_CLIENT_SECRET", "secret")
        monkeypatch.setattr(settings, "WHOOP_REDIRECT_URI", "http://localhost:8000/whoop/callback")
        headers, _ = auth_headers(email=f"connect2-{uuid.uuid4().hex[:8]}@example.com")
        resp = client.get("/whoop/connect", headers=headers)
        assert resp.status_code == 200
        url = resp.json()["authorize_url"]
        assert url.startswith(settings.WHOOP_AUTH_URL)
        assert "client_id=cid" in url
        assert "state=" in url
