"""Application configuration using Pydantic settings.

Mirrors fitness-app/backend/app/core/config.py (SQLite-local default,
env override, Railway production hard-fail guard).
"""
import os

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    APP_NAME: str = Field(default="Oahu Trip")
    DEBUG: bool = Field(default=False)

    DATABASE_URL: str = Field(default="sqlite:///./hawaii.db")

    # Shared-link access control: every /api route except /api/health requires
    # the X-Trip-Token header to match. The family's shared URL carries the
    # token as ?k=<token>; the frontend stores it and sends the header.
    # Empty disables the check (local dev only).
    LINK_TOKEN: str = Field(default="")

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()


def _is_production() -> bool:
    """Detect Railway production. Only the explicit
    RAILWAY_ENVIRONMENT_NAME=production trips the guard."""
    return os.environ.get("RAILWAY_ENVIRONMENT_NAME", "").lower() == "production"


# The shared link is the only access control, so prod must never boot open.
if _is_production() and not settings.LINK_TOKEN:
    raise RuntimeError(
        "LINK_TOKEN must be set in production — the tokenized shared link "
        "is the app's only access control."
    )
