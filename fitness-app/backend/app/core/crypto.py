"""
Symmetric encryption for secrets stored at rest (e.g. WHOOP OAuth tokens).

Uses Fernet (AES-128-CBC + HMAC) with a key derived from ``settings.SECRET_KEY``
so we don't introduce a second secret to manage. The derivation is a SHA-256
of SECRET_KEY, url-safe base64 encoded to Fernet's required 32-byte key format.

Rotating SECRET_KEY invalidates previously stored ciphertext (decrypt raises
``InvalidToken``); the WHOOP service treats an undecryptable token as "needs
reconnect" rather than crashing.
"""
import base64
import hashlib
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Build a Fernet instance from SECRET_KEY (cached per process)."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)  # 32 bytes -> 44-char urlsafe b64
    return Fernet(key)


def encrypt_token(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a token for storage. Returns None for falsy input."""
    if not plaintext:
        return None
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt a stored token. Returns None for falsy input or if the
    ciphertext can't be decrypted (e.g. SECRET_KEY rotated)."""
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None
