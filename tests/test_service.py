"""Unit tests for JobService business logic."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.schemas import JobCreateRequest, RecipientRequest
from app.services.job_service import JobService


def test_new_job_starts_with_pending_status(db_session: Session) -> None:
    """Newly created job starts in 'pending' state with 0 successes/failures."""
    service = JobService(db_session)
    req = JobCreateRequest(
        title="Web Security 101",
        organization="CyberSec Foundation",
        date_of_issue="2026-10-15",
        recipients=[
            RecipientRequest(name="Ada Lovelace", email="ada@example.com"),
            RecipientRequest(name="Alan Turing"),
        ],
    )
    job = service.create_job(req)

    assert job.id is not None
    assert job.status == "pending"
    assert job.total_recipients == 2
    assert job.successful_count == 0
    assert job.failed_count == 0
    assert job.completed_at is None
    assert len(job.certificates) == 2
    assert all(c.status == "pending" for c in job.certificates)


def test_completed_job_has_correct_counts_and_timestamp(
    db_session: Session,
    temp_output_dir: Path,
) -> None:
    """Job counts and completed_at timestamp are accurately set after processing."""

    service = JobService(db_session)
    req = JobCreateRequest(
        title="Async Python Patterns",
        organization="Python Foundation",
        date_of_issue="2026-10-15",
        recipients=[
            RecipientRequest(name="Guido van Rossum"),
            RecipientRequest(name="Raymond Hettinger"),
        ],
    )
    job = service.create_job(req)
    processed_job = service.process_job(job.id)

    assert processed_job.status == "completed"
    assert processed_job.successful_count == 2
    assert processed_job.failed_count == 0
    assert processed_job.completed_at is not None

    for cert in processed_job.certificates:
        assert cert.status == "success"
        assert cert.file_path is not None
        assert Path(cert.file_path).is_file()


def test_process_nonexistent_job_raises_value_error(db_session: Session) -> None:
    """Processing a non-existent job ID raises ValueError."""
    service = JobService(db_session)
    with pytest.raises(ValueError, match="not found"):
        service.process_job("missing-job-uuid")


def test_repository_custom_ids(db_session: Session) -> None:
    """Repository creates entities with explicit IDs."""
    from app.repositories.job_repository import JobRepository

    repo = JobRepository(db_session)
    job = repo.create_job(
        title="Custom ID Job",
        organization="Org",
        date_of_issue="2026-10-15",
        total_recipients=1,
        job_id="custom-job-id-123",
    )
    assert job.id == "custom-job-id-123"

    cert = repo.create_certificate(
        job_id=job.id,
        recipient_name="Special User",
        cert_id="custom-cert-id-456",
    )
    assert cert.id == "custom-cert-id-456"


def test_process_job_idempotent_skips_already_generated(
    db_session: Session,
    temp_output_dir: Path,
) -> None:
    """Repeated processing skips re-generating already created certificates."""
    service = JobService(db_session)
    req = JobCreateRequest(
        title="Distributed Systems",
        organization="Tech Org",
        date_of_issue="2026-10-15",
        recipients=[RecipientRequest(name="Grace Hopper")],
    )
    job = service.create_job(req)
    processed_1 = service.process_job(job.id)
    assert processed_1.successful_count == 1
    cert = processed_1.certificates[0]
    first_mtime = Path(cert.file_path).stat().st_mtime_ns

    # Re-process job - should skip re-generation and preserve existing file
    processed_2 = service.process_job(job.id)
    assert processed_2.successful_count == 1
    second_mtime = Path(cert.file_path).stat().st_mtime_ns
    assert first_mtime == second_mtime


def test_parallel_batch_processing_with_concurrency_limit(
    db_session: Session,
    temp_output_dir: Path,
) -> None:
    """Verify batch with multiple recipients processes concurrently and accurately."""
    service = JobService(db_session)
    service.settings.max_parallel_workers = 4
    req = JobCreateRequest(
        title="High Concurrency Systems",
        organization="Parallel Labs",
        date_of_issue="2026-10-15",
        recipients=[
            RecipientRequest(name=f"Concurrent Recipient {i}") for i in range(12)
        ],
    )
    job = service.create_job(req)
    processed = service.process_job(job.id)

    assert processed.status == "completed"
    assert processed.successful_count == 12
    assert processed.failed_count == 0
    assert len(processed.certificates) == 12
    assert all(c.status == "success" for c in processed.certificates)
    assert all(c.file_path is not None for c in processed.certificates)
