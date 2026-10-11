"""Storage package factory and exports."""

from functools import lru_cache

from app.config import Settings, get_settings
from app.storage.base import (
    StorageBackend,
    StorageError,
    StorageFileNotFoundError,
    StoragePermissionError,
)
from app.storage.local import LocalStorageBackend
from app.storage.s3 import S3StorageBackend


def create_storage_backend(settings: Settings | None = None) -> StorageBackend:
    """Instantiate appropriate storage backend based on configuration."""
    cfg = settings or get_settings()
    backend_type = (cfg.storage_backend or "local").lower().strip()

    if backend_type in ("s3", "rustfs", "minio"):
        return S3StorageBackend(cfg)
    return LocalStorageBackend(cfg)


@lru_cache
def get_storage_backend() -> StorageBackend:
    """Return singleton storage backend instance."""
    return create_storage_backend()


__all__ = [
    "LocalStorageBackend",
    "S3StorageBackend",
    "StorageBackend",
    "StorageError",
    "StorageFileNotFoundError",
    "StoragePermissionError",
    "create_storage_backend",
    "get_storage_backend",
]
