"""Local filesystem storage backend implementation."""

from collections.abc import Generator
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.storage.base import (
    StorageBackend,
    StorageFileNotFoundError,
    StoragePermissionError,
)


class LocalStorageBackend(StorageBackend):
    """Stores certificate files in a local directory on the host filesystem."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_dir = Path(self.settings.output_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, key: str) -> Path:
        """Resolve path and verify it stays within base directory."""
        p = Path(key)
        if p.is_absolute():
            target = p.resolve()
        else:
            clean_key = key.lstrip("/\\")
            target = (self.base_dir / clean_key).resolve()

        try:
            target.relative_to(self.base_dir)
        except ValueError:
            raise StoragePermissionError(
                f"Path traversal detected: '{key}' is outside authorized directory"
            ) from None
        return target

    def upload(
        self, key: str, data: bytes, content_type: str = "application/pdf"
    ) -> str:
        target = self._resolve_safe_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return str(target)

    def get_bytes(self, key: str) -> bytes:
        target = self._resolve_safe_path(key)
        if not target.is_file():
            raise StorageFileNotFoundError(f"File not found: '{key}'")
        return target.read_bytes()

    def stream(self, key: str, chunk_size: int = 65536) -> Generator[bytes, None, None]:
        target = self._resolve_safe_path(key)
        if not target.is_file():
            raise StorageFileNotFoundError(f"File not found: '{key}'")

        with open(target, "rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk

    def delete(self, key: str) -> bool:
        if key.startswith("s3://"):
            return False
        try:
            target = self._resolve_safe_path(key)
        except StoragePermissionError:
            return False

        if target.is_file():
            target.unlink(missing_ok=True)
            return True
        return False

    def exists(self, key: str) -> bool:
        if key.startswith("s3://"):
            return False
        try:
            target = self._resolve_safe_path(key)
            return target.is_file()
        except StoragePermissionError:
            return False

    def get_size(self, key: str) -> int | None:
        if key.startswith("s3://"):
            return None
        try:
            target = self._resolve_safe_path(key)
            if target.is_file():
                return target.stat().st_size
            return None
        except (StoragePermissionError, OSError):
            return None

    def list_objects(self, prefix: str = "") -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if not self.base_dir.is_dir():
            return results

        clean_prefix = prefix.lstrip("/\\")
        for item in self.base_dir.rglob("*.pdf"):
            if not item.is_file():
                continue
            rel = str(item.relative_to(self.base_dir))
            if clean_prefix and not rel.startswith(clean_prefix):
                continue
            try:
                stat = item.stat()
                results.append(
                    {
                        "key": rel,
                        "size": stat.st_size,
                        "last_modified": stat.st_mtime,
                        "path": str(item),
                    }
                )
            except OSError:
                continue
        return results

    def get_stats(self) -> dict[str, Any]:
        total_bytes = 0
        count = 0
        if self.base_dir.is_dir():
            for item in self.base_dir.rglob("*.pdf"):
                if item.is_file():
                    try:
                        total_bytes += item.stat().st_size
                        count += 1
                    except OSError:
                        pass
        return {"total_bytes": total_bytes, "object_count": count}

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        return None
