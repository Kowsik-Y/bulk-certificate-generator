"""Abstract storage backend interface and exceptions for certificate storage."""

from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any


class StorageError(Exception):
    """Base exception for storage backend operations."""


class StorageFileNotFoundError(StorageError):
    """Raised when an object or file is not found in the storage backend."""


class StoragePermissionError(StorageError):
    """Raised when access to a path or object is forbidden."""


class StorageBackend(ABC):
    """Abstract interface for storing, retrieving, and managing certificate files."""

    @abstractmethod
    def upload(
        self, key: str, data: bytes, content_type: str = "application/pdf"
    ) -> str:
        """Store file bytes under key and return stored key/path.

        Args:
            key: Relative identifier/key for the object.
            data: Raw file binary data.
            content_type: MIME media type.

        Returns:
            The stored key/path identifier.
        """
        ...

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        """Retrieve entire object bytes.

        Args:
            key: Relative identifier/key.

        Returns:
            Raw binary data.

        Raises:
            StorageFileNotFoundError: If the key does not exist.
        """
        ...

    @abstractmethod
    def stream(self, key: str, chunk_size: int = 65536) -> Generator[bytes, None, None]:
        """Stream object bytes in chunks for HTTP streaming responses.

        Args:
            key: Relative identifier/key.
            chunk_size: Size of byte chunks to yield.

        Yields:
            Binary chunks.

        Raises:
            StorageFileNotFoundError: If the key does not exist.
        """
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete object from storage.

        Args:
            key: Relative identifier/key.

        Returns:
            True if deleted, False if it was not found.
        """
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check whether object exists in storage."""
        ...

    @abstractmethod
    def get_size(self, key: str) -> int | None:
        """Get object size in bytes, or None if not found."""
        ...

    @abstractmethod
    def list_objects(self, prefix: str = "") -> list[dict[str, Any]]:
        """List stored objects matching prefix."""
        ...

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """Return storage metrics: total_bytes, object_count."""
        ...

    @abstractmethod
    def get_presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        """Generate a presigned download URL if supported, else None."""
        ...
