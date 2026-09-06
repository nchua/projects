"""
Security utilities for password hashing and JWT token management
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# Audience claim on admin tokens (control-plane spec §4.2). ``decode_token``
# passes no ``audience=`` so python-jose rejects any token carrying ``aud`` —
# admin tokens therefore fail on every normal route for free. The enforced
# discriminator is still ``type == "admin"``: jose accepts a token WITHOUT
# ``aud`` when decoding with ``audience=``, so ``aud`` alone cannot gate.
ADMIN_AUDIENCE = "arise-admin"


def _prehash(password: str) -> bytes:
    """
    Pre-hash a password with SHA-256 before bcrypt.

    bcrypt silently truncates inputs past 72 bytes, which means two distinct
    passwords that share a 72-byte prefix would authenticate interchangeably.
    Hashing with SHA-256 first collapses arbitrarily long inputs into a fixed
    32-byte digest (hex-encoded to 64 printable ASCII chars) well under the
    72-byte limit, while preserving entropy from the full input.
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    """Hash a password using SHA-256 pre-hash + bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(_prehash(password), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.

    Tries the new sha256-prehash + bcrypt scheme first, then falls back to
    the legacy raw-bcrypt scheme so existing users' stored hashes (from
    before the prehash rollout) still authenticate. Callers that want to
    transparently upgrade the stored hash should use
    :func:`verify_password_with_rehash` instead.
    """
    ok, _ = verify_password_with_rehash(plain_password, hashed_password)
    return ok


def verify_password_with_rehash(
    plain_password: str, hashed_password: str
) -> Tuple[bool, bool]:
    """
    Verify a password and signal whether the stored hash should be upgraded.

    Returns ``(ok, needs_rehash)``:

    - ``ok`` is True when the password matches either the new (sha256-prehash
      + bcrypt) format or the legacy (raw bcrypt) format.
    - ``needs_rehash`` is True only when verification succeeded via the
      legacy path — callers should re-store ``hash_password(plain_password)``
      so the user is transparently migrated to the new scheme.
    """
    hashed_bytes = hashed_password.encode("utf-8")

    # New format: sha256-prehash then bcrypt.
    try:
        if bcrypt.checkpw(_prehash(plain_password), hashed_bytes):
            return True, False
    except ValueError:
        # Malformed hash — fall through to legacy attempt so we don't crash
        # on historical bad data; the legacy path will also fail cleanly.
        pass

    # Legacy format: raw bcrypt over the password bytes (pre-prehash rollout).
    try:
        if bcrypt.checkpw(plain_password.encode("utf-8"), hashed_bytes):
            return True, True
    except ValueError:
        return False, False

    return False, False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token

    Args:
        data: Dictionary containing user data to encode
        expires_delta: Optional expiration time delta

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Create a JWT refresh token with longer expiration

    Args:
        data: Dictionary containing user data to encode

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT token

    Args:
        token: JWT token string

    Returns:
        Decoded token data or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """
    Verify a token and check its type

    Args:
        token: JWT token string
        token_type: Expected token type ('access' or 'refresh')

    Returns:
        Decoded token data or None if invalid
    """
    payload = decode_token(token)
    if payload is None:
        return None

    # Check token type
    if payload.get("type") != token_type:
        return None

    return payload


# ── Token versioning + admin tokens (control-plane spec §4) ──────────────────

def user_token_claims(user: Any) -> Dict[str, Any]:
    """Claims every token minted for ``user`` must carry: ``sub`` and ``ver``.

    ``ver`` mirrors ``users.token_version``; bumping the column revokes every
    outstanding token (restore, repeated failed step-ups, "log out
    everywhere"). Tokens minted before the column existed carry no ``ver``
    and are treated as version 0 by :func:`token_version_matches`.
    """
    return {"sub": user.id, "ver": user.token_version}


def token_version_matches(payload: Dict[str, Any], user: Any) -> bool:
    """True when the token's ``ver`` equals the user's current ``token_version``."""
    try:
        token_ver = int(payload.get("ver", 0) or 0)
    except (TypeError, ValueError):
        return False
    return token_ver == user.token_version


def create_admin_token(user: Any) -> Tuple[str, datetime]:
    """Mint a short-lived admin token (no refresh token exists for it).

    Claims: ``sub``, ``ver``, ``type="admin"``, ``aud=ADMIN_AUDIENCE``,
    ``iat``, ``exp`` (+``ADMIN_TOKEN_EXPIRE_MINUTES``). Returns the encoded
    token and its expiry.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ADMIN_TOKEN_EXPIRE_MINUTES)
    payload = {
        **user_token_claims(user),
        "type": "admin",
        "aud": ADMIN_AUDIENCE,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM), expire


def decode_admin_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode an admin token; None unless it is a valid admin-type token
    for :data:`ADMIN_AUDIENCE`. Never accepts a normal access/refresh token."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=ADMIN_AUDIENCE,
        )
    except JWTError:
        return None
    if payload.get("type") != "admin" or payload.get("aud") != ADMIN_AUDIENCE:
        return None
    return payload
