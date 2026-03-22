"""Application configuration via environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str

    # Auth
    secret_key: str
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 30

    # Apple Sign In
    apple_team_id: str = ""
    apple_client_id: str = ""

    # Google Routes API
    google_routes_api_key: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Firebase
    firebase_credentials_path: str = ""
    firebase_credentials_json: str = ""  # Raw JSON string (alternative to path)

    # Worker
    worker_db_pool_size: int = 10
    worker_db_max_overflow: int = 40

    # App
    app_name: str = "Depart"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
