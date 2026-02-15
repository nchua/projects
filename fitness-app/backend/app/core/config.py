"""
Application configuration using Pydantic settings
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # App settings
    APP_NAME: str = Field(default="Fitness Tracker API")
    DEBUG: bool = Field(default=True)

    # Database
    DATABASE_URL: str = Field(default="sqlite:///./fitness_app.db")

    # JWT Authentication
    SECRET_KEY: str = Field(default="your-secret-key-here-change-in-production")
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)  # 1 hour

    # Screenshot processing
    SCREENSHOT_PROCESSING_ENABLED: bool = Field(default=True)

    # Scan balance (screenshot scanner monetization)
    FREE_MONTHLY_SCANS: int = Field(default=3)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

# Warn if using default secret key in production
import logging as _logging
_config_logger = _logging.getLogger(__name__)
if not settings.DEBUG and settings.SECRET_KEY == "your-secret-key-here-change-in-production":
    _config_logger.warning(
        "WARNING: Using default SECRET_KEY in non-debug mode. "
        "Set a strong SECRET_KEY environment variable for production."
    )
