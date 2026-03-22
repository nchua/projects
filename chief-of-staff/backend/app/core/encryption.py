"""Fernet encryption for OAuth tokens and other secrets."""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


@lru_cache
def _get_fernet() -> Fernet:
    """Get a cached Fernet instance using the configured encryption key."""
    settings = get_settings()
    key = settings.token_encryption_key
    if not key:
        raise ValueError(
            "TOKEN_ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_token(plaintext: str) -> str:
    """Encrypt a plaintext string using Fernet.

    Args:
        plaintext: The string to encrypt (e.g., an OAuth token).

    Returns:
        The encrypted ciphertext as a URL-safe base64 string.
    """
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted ciphertext string.

    Args:
        ciphertext: The encrypted string to decrypt.

    Returns:
        The original plaintext string.

    Raises:
        InvalidToken: If the ciphertext is invalid or the key is wrong.
    """
    f = _get_fernet()
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def generate_key() -> str:
    """Generate a new Fernet encryption key.

    Returns:
        A URL-safe base64-encoded 32-byte key as a string.
    """
    return Fernet.generate_key().decode("utf-8")
