"""Application configuration via environment variables."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "sqlite:///./chief_of_staff.db"

    # Auth
    secret_key: str = "change-me-to-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # Redis (for ARQ worker)
    redis_url: str = "redis://localhost:6379/0"

    # Anthropic (AI extraction)
    anthropic_api_key: str = ""

    # Token encryption (Fernet key)
    token_encryption_key: str = ""

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""

    # OAuth security
    oauth_redirect_uris: List[str] = []  # Empty = allow all (dev only)

    # Web Push (VAPID)
    vapid_private_key: str = ""
    vapid_claims_email: str = ""

    # App
    app_name: str = "Chief of Staff"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    cors_origins: List[str] = ["*"]

    # Worker
    worker_db_pool_size: int = 10
    worker_db_max_overflow: int = 40


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
