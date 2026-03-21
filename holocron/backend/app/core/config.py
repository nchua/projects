import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    PROJECT_NAME: str = "Holocron"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        "postgresql://localhost:5432/holocron",
    )

    # JWT
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week

    # FSRS defaults
    FSRS_DEFAULT_RETENTION: float = 0.9
    FSRS_AI_CARD_PENALTY: float = 0.82  # 18% shorter initial intervals
    FSRS_DAILY_REVIEW_CAP: int = 30

    class Config:
        env_file = ".env"


settings = Settings()
