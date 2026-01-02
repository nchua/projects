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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=43200)  # 30 days

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
