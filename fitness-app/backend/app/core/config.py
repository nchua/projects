"""
Application configuration using Pydantic settings
"""
import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

DEFAULT_SECRET_KEY = "your-secret-key-here-change-in-production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # App settings
    APP_NAME: str = Field(default="Fitness Tracker API")
    # Default to False — prod must opt-in to debug explicitly. Previously
    # defaulted to True, which leaked stack traces and exposed debug endpoints
    # any time the env var was unset on Railway.
    DEBUG: bool = Field(default=False)

    # Database
    DATABASE_URL: str = Field(default="sqlite:///./fitness_app.db")

    # JWT Authentication
    # Accept either SECRET_KEY or JWT_SECRET_KEY env vars — Railway docs use
    # JWT_SECRET_KEY. Without this alias the prod guard below would RuntimeError
    # if only JWT_SECRET_KEY is set.
    SECRET_KEY: str = Field(
        default=DEFAULT_SECRET_KEY,
        validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET_KEY"),
    )
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)  # 1 hour

    # Screenshot processing
    SCREENSHOT_PROCESSING_ENABLED: bool = Field(default=True)

    # Scan balance (screenshot scanner monetization)
    FREE_MONTHLY_SCANS: int = Field(default=3)

    # APNs push notifications
    APNS_KEY_ID: str = Field(default="")
    APNS_TEAM_ID: str = Field(default="")
    APNS_AUTH_KEY_PATH: str = Field(default="")
    APNS_TOPIC: str = Field(default="com.nickchua.fitnessapp")
    APNS_USE_SANDBOX: bool = Field(default=True)

    # CORS — comma-separated list of allowed origins. When empty the app
    # falls back to the production Railway origin (see main.py) so local
    # dev and existing deploys don't break.
    ALLOWED_ORIGINS: str = Field(default="")

    # ── WHOOP API integration (Phase 1 wearable HR) ──
    # Register a WHOOP developer app at https://developer.whoop.com to obtain a
    # client id/secret, then set these as env vars (never hardcode — see
    # docs/whoop-setup.md). When CLIENT_ID/SECRET are empty the WHOOP endpoints
    # return 503 so the rest of the app keeps working without credentials.
    WHOOP_CLIENT_ID: str = Field(default="")
    WHOOP_CLIENT_SECRET: str = Field(default="")
    # Must exactly match a redirect URI registered on the WHOOP app, e.g.
    # https://backend-production-e316.up.railway.app/whoop/callback
    WHOOP_REDIRECT_URI: str = Field(default="")
    # OAuth scopes. `offline` is required to receive a refresh token; the rest
    # grant read access to the profile (for whoop_user_id) and workouts.
    WHOOP_SCOPES: str = Field(default="offline read:profile read:workout")
    # WHOOP API hosts (overridable for testing / future API changes).
    WHOOP_AUTH_URL: str = Field(default="https://api.prod.whoop.com/oauth/oauth2/auth")
    WHOOP_TOKEN_URL: str = Field(default="https://api.prod.whoop.com/oauth/oauth2/token")
    WHOOP_API_BASE_URL: str = Field(default="https://api.prod.whoop.com/developer")

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()


def _is_production() -> bool:
    """Detect Railway production environment. Only the explicit
    RAILWAY_ENVIRONMENT_NAME=production is treated as prod — other Railway
    envs like staging or preview should not trip the hard-fail guard.
    """
    return os.environ.get("RAILWAY_ENVIRONMENT_NAME", "").lower() == "production"


# Hard-fail at startup if prod is mis-configured. Catching this at import time
# prevents the app from ever booting with a known-insecure config.
if _is_production():
    if settings.SECRET_KEY == DEFAULT_SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is using the insecure default value. "
            "Set SECRET_KEY (or JWT_SECRET_KEY) in the production environment."
        )
    if settings.DEBUG:
        raise RuntimeError(
            "DEBUG=True is not permitted in production. "
            "Unset the DEBUG environment variable or set it to false."
        )
