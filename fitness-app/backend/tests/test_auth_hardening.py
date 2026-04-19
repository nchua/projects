"""Tests for the auth hardening follow-ups from the council review:
- Password policy: min 12 chars + uppercase + lowercase + digit + symbol.
- User search enumeration mitigation: `q` requires min_length=3.
"""
import pytest

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
