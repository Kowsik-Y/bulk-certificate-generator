"""Unit and integration tests for storage backends (Local and S3 / RustFS)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.config import Settings
from app.storage import (
    LocalStorageBackend,
    S3StorageBackend,
    StorageError,
    StorageFileNotFoundError,
    StoragePermissionError,
    create_storage_backend,
    get_storage_backend,
)


def test_storage_backend_factory():
    """create_storage_backend instantiates appropriate backend based on config."""
    local_cfg = Settings(storage_backend="local")
    b1 = create_storage_backend(local_cfg)
    assert isinstance(b1, LocalStorageBackend)

    s3_cfg = Settings(storage_backend="s3", s3_endpoint_url="http://localhost:9000")
    b2 = create_storage_backend(s3_cfg)
    assert isinstance(b2, S3StorageBackend)

    rustfs_cfg = Settings(
        storage_backend="rustfs", s3_endpoint_url="http://localhost:9000"
    )
    b3 = create_storage_backend(rustfs_cfg)
    assert isinstance(b3, S3StorageBackend)

    # Global getter returns an instance
    global_backend = get_storage_backend()
    assert global_backend is not None


def test_local_storage_backend(tmp_path: Path):
    """Test LocalStorageBackend file operations and edge cases."""
    storage_dir = tmp_path / "certs_storage"
    cfg = Settings(output_dir=str(storage_dir))
    backend = LocalStorageBackend(cfg)

    # 1. Upload
    key = "test_sub/sample.pdf"
    content = b"%PDF-1.4 test certificate payload"
    stored_path = backend.upload(key, content)
    assert Path(stored_path).is_file()

    # 2. Exists & Size
    assert backend.exists(key) is True
    assert backend.exists("non_existent.pdf") is False
    assert backend.get_size(key) == len(content)
    assert backend.get_size("non_existent.pdf") is None

    # 3. Get Bytes
    retrieved = backend.get_bytes(key)
    assert retrieved == content

    # 4. Stream
    streamed = b"".join(backend.stream(key, chunk_size=8))
    assert streamed == content

    # 5. List Objects & Stats
    objs = backend.list_objects()
    assert len(objs) == 1
    assert objs[0]["size"] == len(content)

    stats = backend.get_stats()
    assert stats["object_count"] == 1
    assert stats["total_bytes"] == len(content)

    # 6. Presigned URL is None for local
    assert backend.get_presigned_url(key) is None

    # 7. Delete
    assert backend.delete(key) is True
    assert backend.exists(key) is False
    assert backend.delete(key) is False  # already deleted

    # 8. Errors & Traversal
    with pytest.raises(StorageFileNotFoundError):
        backend.get_bytes("ghost.pdf")

    with pytest.raises(StorageFileNotFoundError):
        list(backend.stream("ghost.pdf"))

    with pytest.raises(StoragePermissionError):
        backend.upload("../outside.pdf", b"malicious")

    assert backend.exists("../outside.pdf") is False
    assert backend.delete("../outside.pdf") is False
    assert backend.get_size("../outside.pdf") is None

    # S3 prefix safety in local backend
    assert backend.exists("s3://bucket/test.pdf") is False
    assert backend.delete("s3://bucket/test.pdf") is False
    assert backend.get_size("s3://bucket/test.pdf") is None


def test_s3_storage_backend_mocked(monkeypatch):
    """Test S3StorageBackend (RustFS/S3) operations using mocked boto3 client."""
    mock_boto_client = MagicMock()

    # Mock head_bucket 404 then create_bucket
    def mock_head_bucket(Bucket):
        raise ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket"
        )

    mock_boto_client.head_bucket.side_effect = mock_head_bucket

    monkeypatch.setattr(
        "boto3.client",
        lambda *args, **kwargs: mock_boto_client,
    )

    cfg = Settings(
        storage_backend="s3",
        s3_endpoint_url="http://localhost:9000",
        s3_access_key_id="rustfsadmin",
        s3_secret_access_key="rustfsadmin",
        s3_bucket_name="certificates",
    )
    s3_backend = S3StorageBackend(cfg)

    # 1. Upload & Bucket creation check
    mock_boto_client.put_object.return_value = {"ETag": "12345"}
    result_key = s3_backend.upload("job1/cert1.pdf", b"test pdf content")
    assert result_key == "s3://certificates/job1/cert1.pdf"
    mock_boto_client.create_bucket.assert_called_with(Bucket="certificates")
    mock_boto_client.put_object.assert_called_once()

    # 2. Exists & Size
    mock_boto_client.head_object.return_value = {"ContentLength": 42}
    assert s3_backend.exists("job1/cert1.pdf") is True
    assert s3_backend.get_size("job1/cert1.pdf") == 42

    mock_boto_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404"}}, "HeadObject"
    )
    assert s3_backend.exists("missing.pdf") is False
    assert s3_backend.get_size("missing.pdf") is None

    # Reset head_object
    mock_boto_client.head_object.side_effect = None
    mock_boto_client.head_object.return_value = {"ContentLength": 42}

    # 3. Get Bytes
    mock_body = MagicMock()
    mock_body.read.return_value = b"pdf binary from s3"
    mock_boto_client.get_object.return_value = {"Body": mock_body}

    data = s3_backend.get_bytes("job1/cert1.pdf")
    assert data == b"pdf binary from s3"

    # 4. Stream
    mock_body.iter_chunks.return_value = [b"chunk1", b"chunk2"]
    streamed = b"".join(s3_backend.stream("job1/cert1.pdf"))
    assert streamed == b"chunk1chunk2"

    # 5. Delete
    mock_boto_client.delete_object.return_value = {}
    assert s3_backend.delete("job1/cert1.pdf") is True

    # 6. Presigned URL
    mock_boto_client.generate_presigned_url.return_value = (
        "http://localhost:9000/certificates/job1/cert1.pdf?signature=abc"
    )
    url = s3_backend.get_presigned_url("job1/cert1.pdf")
    assert url is not None
    assert "signature=abc" in url

    # 7. List Objects & Stats
    from datetime import datetime

    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "job1/cert1.pdf",
                    "Size": 1024,
                    "LastModified": datetime(2026, 10, 15, 12, 0, 0),
                },
                {
                    "Key": "job1/cert2.pdf",
                    "Size": 2048,
                    "LastModified": datetime(2026, 10, 15, 12, 1, 0),
                },
            ]
        }
    ]
    mock_boto_client.get_paginator.return_value = mock_paginator

    items = s3_backend.list_objects()
    assert len(items) == 2
    assert items[0]["key"] == "job1/cert1.pdf"

    stats = s3_backend.get_stats()
    assert stats["object_count"] == 2
    assert stats["total_bytes"] == 3072

    # 8. Error handling
    mock_boto_client.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey"}}, "GetObject"
    )
    with pytest.raises(StorageFileNotFoundError):
        s3_backend.get_bytes("nonexistent.pdf")

    mock_boto_client.put_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied"}}, "PutObject"
    )
    with pytest.raises(StorageError):
        s3_backend.upload("job/fail.pdf", b"data")


def test_job_service_s3_storage_processing(db_session, monkeypatch):
    """Test JobService when configured with S3 / RustFS storage."""
    from app.schemas import JobCreateRequest, RecipientRequest
    from app.services.job_service import JobService

    mock_s3 = MagicMock(spec=S3StorageBackend)
    mock_s3.upload.return_value = "s3://certificates/test-job/cert-1.pdf"
    mock_s3.exists.return_value = True
    mock_s3.get_size.return_value = 5432
    mock_s3.get_bytes.return_value = b"%PDF-1.4 s3 data"
    mock_s3.get_presigned_url.return_value = "http://localhost:9000/download-presigned"
    mock_s3.get_stats.return_value = {"total_bytes": 5432, "object_count": 1}

    s3_settings = Settings(
        storage_backend="s3",
        s3_bucket_name="certificates",
    )

    service = JobService(db=db_session, storage=mock_s3)
    service.settings = s3_settings

    req = JobCreateRequest(
        title="RustFS Cloud Engineering",
        organization="RustFS Academy",
        date_of_issue="2026-10-15",
        recipients=[RecipientRequest(name="Ferris Crab", email="ferris@rust-lang.org")],
    )
    job = service.create_job(req)
    processed = service.process_job(job.id)

    assert processed.status == "completed"
    assert processed.successful_count == 1
    cert = processed.certificates[0]
    assert cert.file_path == "s3://certificates/test-job/cert-1.pdf"
    mock_s3.upload.assert_called_once()

    # List certificate files returns presigned url and s3 backend info
    listing = service.list_certificate_files(job_id=job.id)
    assert len(listing.items) == 1
    assert listing.items[0].storage_backend == "s3"
    assert listing.items[0].presigned_url == "http://localhost:9000/download-presigned"

    # Zip generation reads from mock_s3.get_bytes
    zip_path = service.create_job_zip(job.id)
    assert zip_path.is_file()

    # System stats returns s3 details
    stats = service.get_system_stats()
    assert stats.storage_backend == "s3"
    assert stats.bucket_name == "certificates"
    assert stats.total_storage_bytes == 5432

    # Clean up zip
    zip_path.unlink(missing_ok=True)


def test_s3_streaming_api_endpoints(client, db_session, monkeypatch):
    """Test API download and preview endpoints when streaming from S3/RustFS."""
    from app.models import Certificate, Job

    job = Job(
        title="S3 Job",
        organization="S3 Org",
        date_of_issue="2026-10-15",
        total_recipients=1,
        successful_count=1,
    )
    db_session.add(job)
    db_session.flush()

    cert = Certificate(
        job_id=job.id,
        recipient_name="S3 User",
        status="success",
        file_path="s3://certificates/test/cert.pdf",
    )
    db_session.add(cert)
    db_session.commit()

    mock_s3 = MagicMock(spec=S3StorageBackend)
    mock_s3.exists.return_value = True
    mock_s3.stream.return_value = iter([b"%PDF-1.4 s3 stream content"])

    monkeypatch.setattr(
        "app.routers.jobs.LocalStorageBackend",
        tuple(),
    )
    monkeypatch.setattr(
        "app.services.job_service.create_storage_backend",
        lambda s=None: mock_s3,
    )

    # Test download streaming
    r_dl = client.get(f"/api/certificates/{cert.id}/download/")
    assert r_dl.status_code == 200
    assert r_dl.headers["content-type"] == "application/pdf"
    assert "S3_User" in r_dl.headers.get("content-disposition", "")
    assert b"%PDF-1.4 s3 stream content" in r_dl.content

    # Test preview streaming
    mock_s3.stream.return_value = iter([b"%PDF-1.4 s3 preview content"])
    r_prev = client.get(f"/api/certificates/{cert.id}/preview/")
    assert r_prev.status_code == 200
    assert "inline" in r_prev.headers.get("content-disposition", "")
    assert b"%PDF-1.4 s3 preview content" in r_prev.content
