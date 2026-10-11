"""S3-compatible storage backend supporting RustFS, MinIO, and AWS S3."""

import logging
from collections.abc import Generator
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import Settings, get_settings
from app.storage.base import (
    StorageBackend,
    StorageError,
    StorageFileNotFoundError,
)

logger = logging.getLogger(__name__)


class S3StorageBackend(StorageBackend):
    """Stores certificate files in an S3-compatible bucket (RustFS / MinIO / S3)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.bucket_name = self.settings.s3_bucket_name or "certificates"

        client_kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": self.settings.s3_region_name or "us-east-1",
            "use_ssl": self.settings.s3_use_ssl,
            "config": Config(s3={"addressing_style": "path"}),
        }

        if self.settings.s3_endpoint_url:
            client_kwargs["endpoint_url"] = self.settings.s3_endpoint_url
        if self.settings.s3_access_key_id:
            client_kwargs["aws_access_key_id"] = self.settings.s3_access_key_id
        if self.settings.s3_secret_access_key:
            client_kwargs["aws_secret_access_key"] = self.settings.s3_secret_access_key

        self.client = boto3.client(**client_kwargs)
        self._bucket_verified = False

    def _normalize_key(self, key: str) -> str:
        """Strip leading slashes and s3://bucket/ prefixes from object keys."""
        k = key.strip()
        prefix = f"s3://{self.bucket_name}/"
        if k.startswith(prefix):
            k = k[len(prefix) :]
        elif k.startswith("s3://"):
            # Strip unknown s3://bucket/ prefix
            parts = k[5:].split("/", 1)
            k = parts[1] if len(parts) > 1 else parts[0]
        return k.lstrip("/\\")

    def ensure_bucket_exists(self) -> None:
        """Verify the configured bucket exists, creating it if needed."""
        if self._bucket_verified:
            return

        try:
            self.client.head_bucket(Bucket=self.bucket_name)
            self._bucket_verified = True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchBucket"):
                logger.info(
                    "Bucket '%s' not found. Creating bucket on RustFS / S3...",
                    self.bucket_name,
                )
                try:
                    self.client.create_bucket(Bucket=self.bucket_name)
                    self._bucket_verified = True
                except Exception as create_err:
                    raise StorageError(
                        f"Failed to create bucket '{self.bucket_name}': {create_err}"
                    ) from create_err
            else:
                logger.warning("head_bucket failed with code %s: %s", error_code, exc)
                # Still mark as verified to avoid hammering on temporary network issues
                self._bucket_verified = True

    def upload(
        self, key: str, data: bytes, content_type: str = "application/pdf"
    ) -> str:
        self.ensure_bucket_exists()
        clean_key = self._normalize_key(key)
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=clean_key,
                Body=data,
                ContentType=content_type,
            )
            return f"s3://{self.bucket_name}/{clean_key}"
        except ClientError as e:
            raise StorageError(f"S3 upload error for key '{clean_key}': {e}") from e

    def get_bytes(self, key: str) -> bytes:
        clean_key = self._normalize_key(key)
        try:
            resp = self.client.get_object(
                Bucket=self.bucket_name,
                Key=clean_key,
            )
            body = resp["Body"]
            return body.read()
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                raise StorageFileNotFoundError(
                    f"S3 object '{clean_key}' not found"
                ) from e
            raise StorageError(f"S3 fetch error for '{clean_key}': {e}") from e

    def stream(self, key: str, chunk_size: int = 65536) -> Generator[bytes, None, None]:
        clean_key = self._normalize_key(key)
        try:
            resp = self.client.get_object(
                Bucket=self.bucket_name,
                Key=clean_key,
            )
            body = resp["Body"]
            for chunk in body.iter_chunks(chunk_size):
                yield chunk
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                raise StorageFileNotFoundError(
                    f"S3 object '{clean_key}' not found"
                ) from e
            raise StorageError(f"S3 stream error for '{clean_key}': {e}") from e

    def delete(self, key: str) -> bool:
        clean_key = self._normalize_key(key)
        try:
            self.client.delete_object(
                Bucket=self.bucket_name,
                Key=clean_key,
            )
            return True
        except ClientError as e:
            logger.warning("S3 delete failed for '%s': %s", clean_key, e)
            return False

    def exists(self, key: str) -> bool:
        clean_key = self._normalize_key(key)
        try:
            self.client.head_object(
                Bucket=self.bucket_name,
                Key=clean_key,
            )
            return True
        except ClientError:
            return False

    def get_size(self, key: str) -> int | None:
        clean_key = self._normalize_key(key)
        try:
            resp = self.client.head_object(
                Bucket=self.bucket_name,
                Key=clean_key,
            )
            return resp.get("ContentLength")
        except ClientError:
            return None

    def list_objects(self, prefix: str = "") -> list[dict[str, Any]]:
        clean_prefix = self._normalize_key(prefix)
        results: list[dict[str, Any]] = []
        paginator = self.client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(
                Bucket=self.bucket_name, Prefix=clean_prefix
            ):
                for item in page.get("Contents", []):
                    results.append(
                        {
                            "key": item["Key"],
                            "size": item["Size"],
                            "last_modified": item["LastModified"].isoformat(),
                            "path": f"s3://{self.bucket_name}/{item['Key']}",
                        }
                    )
        except ClientError as e:
            logger.warning("S3 list_objects error: %s", e)
        return results

    def get_stats(self) -> dict[str, Any]:
        total_bytes = 0
        count = 0
        paginator = self.client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self.bucket_name):
                for item in page.get("Contents", []):
                    total_bytes += item.get("Size", 0)
                    count += 1
        except ClientError as e:
            logger.warning("S3 get_stats error: %s", e)
        return {"total_bytes": total_bytes, "object_count": count}

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        clean_key = self._normalize_key(key)
        try:
            url: str = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": clean_key},
                ExpiresIn=expires_in,
            )
            # Rewrite Docker internal hostname to localhost for browser clients
            if "://rustfs:9000" in url:
                url = url.replace("://rustfs:9000", "://localhost:9000")
            return url
        except ClientError as e:
            logger.warning("S3 generate_presigned_url error: %s", e)
            return None
