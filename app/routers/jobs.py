"""API router endpoints for bulk certificate jobs and certificate downloads."""

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas import (
    CertificateResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
)
from app.services.job_service import JobService
from app.tasks import process_job_task

router = APIRouter(tags=["Certificates & Jobs"])


def sanitize_filename(name: str) -> str:
    """Sanitize recipient name for safe HTTP attachment filename."""
    clean = re.sub(r"[^\w\s-]", "", name).strip()
    return re.sub(r"[-\s]+", "_", clean) or "recipient"


@router.post(
    "/api/jobs/",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit bulk certificate generation job",
    description=(
        "Accepts certificate metadata and recipient details, creates "
        "a pending job in the database, and dispatches a Celery task "
        "for background processing."
    ),
)
def create_job(
    request: JobCreateRequest,
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """Create a bulk certificate generation job and dispatch Celery worker task."""
    service = JobService(db)
    job = service.create_job(request)

    # Dispatch Celery background task
    task = process_job_task.delay(job.id)
    service.update_job_task_id(job.id, task.id)

    return JobCreateResponse(
        job_id=job.id,
        status="pending",
        message=(
            f"Job created. {job.total_recipients} certificates queued for generation."
        ),
    )


@router.get(
    "/api/jobs/{job_id}/",
    response_model=JobStatusResponse,
    summary="Get job processing status and progress",
    description=(
        "Retrieve generation status, recipient totals, and progress metrics for a job."
    ),
)
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
) -> JobStatusResponse:
    """Check the status and progress metrics of a certificate generation job."""
    service = JobService(db)
    job = service.get_job_status(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return JobStatusResponse.model_validate(job)


@router.get(
    "/api/jobs/{job_id}/certificates/",
    response_model=list[CertificateResponse],
    summary="List all certificates for a job",
    description=(
        "Retrieve all recipient certificate records (including status and errors)."
    ),
)
def get_certificates(
    job_id: str,
    db: Session = Depends(get_db),
) -> list[CertificateResponse]:
    """List all individual certificates and their statuses for a given job."""
    service = JobService(db)
    job = service.get_job_status(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    certs = service.get_certificates(job_id)
    return [CertificateResponse.model_validate(cert) for cert in certs]


@router.get(
    "/api/certificates/{certificate_id}/download/",
    summary="Download a generated certificate PDF",
    description="Download the generated PDF certificate binary for a certificate ID.",
)
def download_certificate(
    certificate_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download the generated PDF for an individual recipient."""
    service = JobService(db)
    cert = service.get_certificate_by_id(certificate_id)
    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{certificate_id}' not found",
        )

    if cert.status != "success" or not cert.file_path:
        error_detail = (
            cert.error_message or "Certificate is not ready or generation failed"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Certificate not available: {error_detail}",
        )

    settings = get_settings()
    file_path = Path(cert.file_path).resolve()
    base_storage = Path(settings.output_dir).resolve()

    # Path traversal security protection
    try:
        file_path.relative_to(base_storage)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: file path is outside authorized storage directory",
        ) from None

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate PDF file is missing from storage",
        )

    safe_name = sanitize_filename(cert.recipient_name)
    download_filename = f"certificate_{safe_name}.pdf"

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=download_filename,
    )
