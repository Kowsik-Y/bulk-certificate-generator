"""Configuration settings for Bulk Certificate Generator."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment or defaults."""

    database_url: str = "sqlite:///./certificates.db"
    redis_url: str = "redis://localhost:6379/0"
    output_dir: str = "/tmp/bulk_certificates_output"
    app_title: str = "Bulk Certificate Generator API"
    app_version: str = "0.1.0"
    max_recipients_per_batch: int = 1000
    max_parallel_workers: int = 5

    # Storage Backend Configuration (RustFS / MinIO / S3 / Local)
    storage_backend: str = "local"  # "local", "s3", "rustfs", "minio"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket_name: str = "certificates"
    s3_region_name: str = "us-east-1"
    s3_use_ssl: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
