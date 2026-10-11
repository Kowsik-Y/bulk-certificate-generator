"""Tests for partial failure isolation and error resilience."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.schemas import JobCreateRequest, RecipientRequest
from app.services.job_service import JobService


def test_one_failure_does_not_block_others(
    db_session: Session,
    temp_output_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If one recipient certificate fails, others still succeed."""
    service = JobService(db_session)
    req = JobCreateRequest(
        title="Distributed Systems",
        organization="Cloud Org",
        date_of_issue="2026-10-15",
        recipients=[
            RecipientRequest(name="Good Recipient 1"),
            RecipientRequest(name="Failing Recipient"),
            RecipientRequest(name="Good Recipient 2"),
        ],
    )
    job = service.create_job(req)

    from app.generator import certificate_generator

    original_generate = certificate_generator.generate_certificate

    def mock_generate(recipient_name: str, **kwargs):
        if recipient_name == "Failing Recipient":
            raise RuntimeError("Simulated render engine crash for test")
        return original_generate(recipient_name=recipient_name, **kwargs)

    monkeypatch.setattr(
        "app.services.job_service.generate_certificate",
        mock_generate,
    )

    processed_job = service.process_job(job.id)

    assert processed_job.status == "completed_with_errors"
    assert processed_job.successful_count == 2
    assert processed_job.failed_count == 1

    certs = {c.recipient_name: c for c in processed_job.certificates}
    assert certs["Good Recipient 1"].status == "success"
    assert certs["Good Recipient 2"].status == "success"
    assert certs["Failing Recipient"].status == "failed"
    assert "Simulated render engine crash" in certs["Failing Recipient"].error_message
    assert certs["Failing Recipient"].file_path is None


def test_all_failures_still_marks_job_terminal(
    db_session: Session,
    temp_output_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All certificates failing marks job as completed_with_errors."""

    service = JobService(db_session)
    req = JobCreateRequest(
        title="Distributed Systems",
        organization="Cloud Org",
        date_of_issue="2026-10-15",
        recipients=[
            RecipientRequest(name="Recipient A"),
            RecipientRequest(name="Recipient B"),
        ],
    )
    job = service.create_job(req)

    def failing_generate(**kwargs):
        raise OSError("Disk quota exceeded simulation")

    monkeypatch.setattr(
        "app.services.job_service.generate_certificate",
        failing_generate,
    )

    processed_job = service.process_job(job.id)

    assert processed_job.status == "completed_with_errors"
    assert processed_job.successful_count == 0
    assert processed_job.failed_count == 2
    assert processed_job.completed_at is not None
    assert all(c.status == "failed" for c in processed_job.certificates)
    assert all(
        "Disk quota" in (c.error_message or "") for c in processed_job.certificates
    )
