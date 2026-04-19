"""Tests for the auth hardening follow-ups from the council review:
- Password policy: min 12 chars + uppercase + lowercase + digit + symbol.
- User search enumeration mitigation: `q` requires min_length=3.
- bcrypt 72-byte truncation closed via SHA-256 pre-hash.
- /auth/register does not leak whether an email is already registered.
- Legacy raw-bcrypt hashes still verify and are transparently upgraded
  to the new sha256-prehash + bcrypt scheme on next successful login.
"""
import bcrypt
import pytest

from app.core.security import (
    hash_password,
    verify_password,
    verify_password_with_rehash,
)
from app.schemas.auth import UserRegister


class TestPasswordPolicy:
    def test_rejects_short_password(self):
        with pytest.raises(ValueError, match="at least 12 characters"):
            UserRegister(email="t@example.com", password="Ab1!abcd")  # 8 chars

    def test_rejects_missing_symbol(self):
        with pytest.raises(ValueError, match="symbol"):
            UserRegister(email="t@example.com", password="Abcdefgh12ab")  # 12 but no symbol

    def test_rejects_missing_digit(self):
        with pytest.raises(ValueError, match="digit"):
            UserRegister(email="t@example.com", password="Abcdefghijk!")

    def test_rejects_missing_uppercase(self):
        with pytest.raises(ValueError, match="uppercase"):
            UserRegister(email="t@example.com", password="abcdefgh1234!")

    def test_rejects_missing_lowercase(self):
        with pytest.raises(ValueError, match="lowercase"):
            UserRegister(email="t@example.com", password="ABCDEFGH1234!")

    def test_accepts_strong_password(self):
        u = UserRegister(email="t@example.com", password="Str0ng-Pass1234")
        assert u.password == "Str0ng-Pass1234"


class TestUserSearchMinLength:
    def test_single_char_query_rejected(self, client, auth_headers):
        """Short queries enable userbase enumeration — must 422."""
        response = client.get("/users/search?q=a", headers=auth_headers)
        assert response.status_code == 422, response.text

    def test_two_char_query_rejected(self, client, auth_headers):
        response = client.get("/users/search?q=ab", headers=auth_headers)
        assert response.status_code == 422, response.text

    def test_three_char_query_accepted(self, client, auth_headers):
        """Three characters is the minimum for a real 'find a friend' query."""
        response = client.get("/users/search?q=abc", headers=auth_headers)
        assert response.status_code == 200, response.text

    def test_search_still_requires_auth(self, client):
        response = client.get("/users/search?q=abc")
        assert response.status_code == 401


class TestBcryptTruncation:
    """
    bcrypt silently truncates inputs past 72 bytes. If we hand the raw
    password to bcrypt, two passwords that share a 72-byte prefix verify
    against each other's hash. We defend by SHA-256 pre-hashing first.
    """

    def test_long_passwords_with_shared_72_byte_prefix_do_not_collide(self):
        # 72-byte shared prefix + differing suffix. Under raw bcrypt these
        # would be indistinguishable; under sha256-prehash + bcrypt they
        # must not collide.
        prefix = "A" * 72
        pw_a = prefix + "DIFFERENT_SUFFIX_A!1"
        pw_b = prefix + "DIFFERENT_SUFFIX_B!1"
        hashed_a = hash_password(pw_a)
        assert verify_password(pw_a, hashed_a) is True
        assert verify_password(pw_b, hashed_a) is False

    def test_password_longer_than_72_bytes_still_verifies(self):
        pw = "P@ssword1" + ("x" * 200)  # well over 72 bytes
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True
        assert verify_password(pw[:-1], hashed) is False

    def test_multibyte_unicode_password_round_trip(self):
        # 100 chars of multibyte UTF-8 blows past 72 bytes easily.
        pw = ("Z\u00e9lda!1" + "\u2603") * 20
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True


class TestLegacyHashMigration:
    """
    Hashes created before the sha256-prehash rollout are raw-bcrypt over the
    password bytes. They must keep working (no forced password reset) and
    get transparently upgraded on next successful verify.
    """

    @staticmethod
    def _legacy_hash(password: str) -> str:
        return bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def test_legacy_hash_verifies(self):
        pw = "LegacyPass123!"
        legacy = self._legacy_hash(pw)
        assert verify_password(pw, legacy) is True
        assert verify_password("WrongPass1!", legacy) is False

    def test_legacy_hash_signals_needs_rehash(self):
        pw = "LegacyPass123!"
        legacy = self._legacy_hash(pw)
        ok, needs_rehash = verify_password_with_rehash(pw, legacy)
        assert ok is True
        assert needs_rehash is True

    def test_new_hash_does_not_signal_needs_rehash(self):
        pw = "FreshPass123!"
        fresh = hash_password(pw)
        ok, needs_rehash = verify_password_with_rehash(pw, fresh)
        assert ok is True
        assert needs_rehash is False

    def test_malformed_hash_returns_false_not_raises(self):
        ok, needs_rehash = verify_password_with_rehash("whatever", "not-a-bcrypt-hash")
        assert ok is False
        assert needs_rehash is False


class TestRegisterEnumerationResistance:
    """
    /auth/register must not reveal whether an email is already registered.
    Status code and response shape must match between fresh and duplicate
    registrations; the real user's id / created_at must never be echoed back
    on a duplicate probe.
    """

    def test_fresh_and_duplicate_register_share_shape(self, client, create_test_user):
        existing_user, _ = create_test_user(
            email="known@example.com", password="RealPass123!"
        )
        fresh = client.post("/auth/register", json={
            "email": "brandnew@example.com",
            "password": "StrongPass1!",
        })
        dupe = client.post("/auth/register", json={
            "email": "known@example.com",
            "password": "AttackerGuess1!",
        })
        assert fresh.status_code == dupe.status_code == 201
        assert fresh.json().keys() == dupe.json().keys()
        assert fresh.json()["message"] == dupe.json()["message"]
        # Same user subfields present in both.
        assert set(fresh.json()["user"].keys()) == set(dupe.json()["user"].keys())
        # CRITICAL: the duplicate response must not leak the real user id.
        assert dupe.json()["user"]["id"] != existing_user.id

    def test_duplicate_register_does_not_overwrite_password(self, client, create_test_user):
        _, original = create_test_user(
            email="overwrite@example.com", password="OriginalPass1!"
        )
        client.post("/auth/register", json={
            "email": "overwrite@example.com",
            "password": "AttackerPass1!",
        })
        # Attacker password rejected.
        bad = client.post("/auth/login", json={
            "email": "overwrite@example.com",
            "password": "AttackerPass1!",
        })
        assert bad.status_code == 401
        # Original password still works.
        good = client.post("/auth/login", json={
            "email": "overwrite@example.com",
            "password": original,
        })
        assert good.status_code == 200


class TestLoginTransparentRehash:
    """On successful login, a legacy-format stored hash is upgraded."""

    def test_login_upgrades_legacy_hash(self, client, db):
        from app.models.user import User, UserProfile

        pw = "LegacyUserPass1!"
        legacy_hash = bcrypt.hashpw(
            pw.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        user = User(email="legacy@example.com", password_hash=legacy_hash)
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(UserProfile(user_id=user.id))
        db.commit()

        response = client.post("/auth/login", json={
            "email": "legacy@example.com",
            "password": pw,
        })
        assert response.status_code == 200, response.text

        db.expire_all()
        refreshed = db.query(User).filter(User.id == user.id).first()
        # Hash string should have changed (new scheme stores a different
        # bcrypt digest derived from the sha256 hex prehash).
        assert refreshed.password_hash != legacy_hash
        # And the new hash must still verify the same password.
        assert verify_password(pw, refreshed.password_hash) is True
        # And it should no longer be flagged for rehash.
        _, needs_rehash = verify_password_with_rehash(pw, refreshed.password_hash)
        assert needs_rehash is False
