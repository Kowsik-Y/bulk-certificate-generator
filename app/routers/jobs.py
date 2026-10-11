"""API router endpoints for bulk certificate jobs and certificate downloads."""

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas import (
    CertificateListResponse,
    CertificateResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
    SystemStatsResponse,
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


@router.get(
    "/api/jobs/",
    response_model=list[JobStatusResponse],
    summary="List all certificate generation jobs",
    description=(
        "Retrieve all submitted generation jobs with status and progress metrics."
    ),
)
def list_jobs(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[JobStatusResponse]:
    """List submitted jobs ordered by creation date."""
    service = JobService(db)
    jobs = service.list_jobs(skip=skip, limit=limit)
    return [JobStatusResponse.model_validate(j) for j in jobs]


@router.get(
    "/api/jobs/{job_id}/download-zip/",
    summary="Download all certificates for a job as a ZIP archive",
    description=(
        "Packages all successfully generated certificates into a single zip file."
    ),
)
def download_job_zip(
    job_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download a ZIP archive containing all certificates generated for a job."""
    service = JobService(db)
    job = service.get_job_status(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    try:
        zip_path = service.create_job_zip(job_id)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from None

    safe_title = sanitize_filename(job.title)
    zip_filename = f"{safe_title}_certificates.zip"

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=zip_filename,
    )


@router.get(
    "/api/certificates/",
    response_model=CertificateListResponse,
    summary="List and filter certificate files",
    description="Query certificates with search, status filters, and file metadata.",
)
def list_certificates(
    job_id: str | None = None,
    status_filter: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> CertificateListResponse:
    """List certificates enriched with file sizes and management URLs."""
    service = JobService(db)
    return service.list_certificate_files(
        job_id=job_id,
        status=status_filter,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/api/certificates/{certificate_id}/preview/",
    summary="Preview a generated certificate PDF inline",
    description=(
        "Renders PDF binary inline in the browser without download attachment header."
    ),
)
def preview_certificate(
    certificate_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    """View certificate PDF inline in browser for preview modals."""
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

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@router.delete(
    "/api/certificates/{certificate_id}/",
    status_code=status.HTTP_200_OK,
    summary="Delete a certificate and its stored file",
    description=(
        "Removes the certificate record from the database and deletes its PDF file."
    ),
)
def delete_certificate(
    certificate_id: str,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Delete certificate file and record from the system."""
    service = JobService(db)
    deleted = service.delete_certificate(certificate_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{certificate_id}' not found",
        )
    return {
        "status": "success",
        "message": f"Certificate '{certificate_id}' deleted successfully",
    }


@router.get(
    "/api/stats/",
    response_model=SystemStatsResponse,
    summary="Get system storage and job statistics",
    description=(
        "Aggregated count of jobs, certificates, success rates, and disk space used."
    ),
)
def get_system_stats(
    db: Session = Depends(get_db),
) -> SystemStatsResponse:
    """Retrieve system-wide metrics and total storage usage."""
    service = JobService(db)
    return service.get_system_stats()
