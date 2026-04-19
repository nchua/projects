"""
Security utilities for password hashing and JWT token management
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


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

    to_encode.update({"exp": expire, "type": "access"})
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
    expire = datetime.now(timezone.utc) + timedelta(days=7)  # Refresh tokens last 7 days
    to_encode.update({"exp": expire, "type": "refresh"})
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
