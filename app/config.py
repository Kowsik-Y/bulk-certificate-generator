"""Configuration settings for Bulk Certificate Generator."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment or defaults."""

    database_url: str = "sqlite:///./certificates.db"
    redis_url: str = "redis://localhost:6379/0"
    output_dir: str = "./output"
    app_title: str = "Bulk Certificate Generator API"
    app_version: str = "0.1.0"
    max_recipients_per_batch: int = 1000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
