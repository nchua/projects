"""Security utilities: password hashing, JWT tokens, Apple Sign-In verification."""

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt as pyjwt
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Cache for Apple's JWKS keys
_apple_jwks_cache: dict[str, Any] = {"keys": None, "fetched_at": None}
_APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_APPLE_JWKS_CACHE_SECONDS = 86400  # 24 hours


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    """Create a short-lived JWT access token.

    Args:
        data: Payload dict. Must include 'sub' (user ID).

    Returns:
        Encoded JWT string.
    """
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    now = datetime.now(timezone.utc)
    to_encode.update({"exp": expire, "type": "access", "iat": now})
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


def create_refresh_token(data: dict) -> str:
    """Create a long-lived JWT refresh token.

    Args:
        data: Payload dict. Must include 'sub' (user ID).

    Returns:
        Encoded JWT string.
    """
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    now = datetime.now(timezone.utc)
    to_encode.update({"exp": expire, "type": "refresh", "iat": now})
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Decode and verify a JWT token.

    Args:
        token: Encoded JWT string.

    Returns:
        Decoded payload dict.

    Raises:
        JWTError: If token is invalid or expired.
    """
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])


async def _fetch_apple_jwks() -> dict[str, Any]:
    """Fetch Apple's JSON Web Key Set, with 24-hour caching."""
    now = datetime.now(timezone.utc)
    if (
        _apple_jwks_cache["keys"] is not None
        and _apple_jwks_cache["fetched_at"] is not None
        and (now - _apple_jwks_cache["fetched_at"]).total_seconds()
        < _APPLE_JWKS_CACHE_SECONDS
    ):
        return _apple_jwks_cache["keys"]

    async with httpx.AsyncClient() as client:
        response = await client.get(_APPLE_JWKS_URL, timeout=10.0)
        response.raise_for_status()
        jwks = response.json()

    _apple_jwks_cache["keys"] = jwks
    _apple_jwks_cache["fetched_at"] = now
    return jwks


async def verify_apple_identity_token(identity_token: str) -> dict[str, Any]:
    """Verify an Apple Sign-In identity token and return its claims.

    Fetches Apple's JWKS, finds the matching key by `kid`, verifies the JWT
    signature, issuer, audience, and expiration.

    Args:
        identity_token: The JWT from ASAuthorizationAppleIDCredential.identityToken.

    Returns:
        Dict with claims including 'sub' (Apple user ID) and 'email'.

    Raises:
        ValueError: If token verification fails.
    """
    settings = get_settings()

    try:
        # Decode the header to find the key ID
        unverified_header = pyjwt.get_unverified_header(identity_token)
        kid = unverified_header.get("kid")
        if not kid:
            raise ValueError("Apple identity token missing 'kid' header")

        # Fetch Apple's public keys
        jwks = await _fetch_apple_jwks()

        # Find the matching key
        matching_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                matching_key = key
                break

        if matching_key is None:
            raise ValueError(
                f"No matching Apple public key found for kid: {kid}"
            )

        # Construct the public key from JWK
        public_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(matching_key)

        # Verify and decode the token
        claims = pyjwt.decode(
            identity_token,
            public_key,
            algorithms=["RS256"],
            audience=settings.apple_client_id,
            issuer="https://appleid.apple.com",
            options={"verify_exp": True},
        )

        return claims

    except pyjwt.ExpiredSignatureError:
        raise ValueError("Apple identity token has expired")
    except pyjwt.InvalidTokenError as e:
        raise ValueError(f"Invalid Apple identity token: {e}")
    except httpx.HTTPError as e:
        raise ValueError(f"Failed to fetch Apple JWKS: {e}")
