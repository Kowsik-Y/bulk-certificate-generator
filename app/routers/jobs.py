import csv
import io
import json
import re
from pathlib import Path
from typing import Any

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas import (
    CertificateListResponse,
    CertificateResponse,
    DownloadSelectedZipRequest,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
    ParseRecipientsResponse,
    RecipientRequest,
    SystemStatsResponse,
)
from app.services.job_service import JobService
from app.storage.local import LocalStorageBackend
from app.tasks import process_job_task

router = APIRouter(tags=["Certificates & Jobs"])


def sanitize_filename(name: str) -> str:
    """Sanitize recipient name for safe HTTP attachment filename."""
    clean = re.sub(r"[^\w\s-]", "", name).strip()
    return re.sub(r"[-\s]+", "_", clean) or "recipient"


def parse_recipients_from_bytes(
    filename: str, content: bytes
) -> list[RecipientRequest]:
    """Parse recipient records from JSON, CSV, or Excel bytes."""
    ext = Path(filename).suffix.lower()
    recipients: list[RecipientRequest] = []

    def _extract_dict(item: dict[str, Any]) -> RecipientRequest | None:
        name = (
            item.get("name")
            or item.get("recipient_name")
            or item.get("FullName")
            or item.get("full_name")
            or item.get("Name")
            or item.get("Recipient")
            or ""
        )
        if not isinstance(name, str) or not name.strip():
            return None
        email = (
            item.get("email")
            or item.get("recipient_email")
            or item.get("Email")
            or item.get("Mail")
            or None
        )
        if email and isinstance(email, str):
            email = email.strip() or None
        else:
            email = None
        try:
            return RecipientRequest(name=name.strip(), email=email)
        except Exception:
            return None

    if ext == ".json":
        try:
            parsed = json.loads(content.decode("utf-8-sig"))
            if isinstance(parsed, dict) and "recipients" in parsed:
                parsed = parsed["recipients"]
            if not isinstance(parsed, list):
                raise ValueError(
                    "JSON must be a list of recipients or an object with "
                    "'recipients' array."
                )
            for row in parsed:
                if isinstance(row, dict):
                    rec = _extract_dict(row)
                    if rec:
                        recipients.append(rec)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON format: {e}",
            ) from e

    elif ext in [".csv", ".txt"]:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        reader = csv.reader(io.StringIO(text))
        rows = [r for r in reader if any(c.strip() for c in r)]
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV file is empty.",
            )
        first_row = [c.strip().lower() for c in rows[0]]
        name_idx = -1
        email_idx = -1
        for idx, col in enumerate(first_row):
            if col in ["name", "recipient_name", "full name", "fullname", "recipient"]:
                name_idx = idx
            elif col in ["email", "recipient_email", "mail", "e-mail"]:
                email_idx = idx

        start_row = 1 if name_idx != -1 else 0
        if name_idx == -1:
            name_idx = 0
            email_idx = 1 if len(rows[0]) > 1 else -1

        for row in rows[start_row:]:
            if not row or len(row) <= name_idx:
                continue
            name_val = row[name_idx].strip()
            if not name_val:
                continue
            email_val = (
                row[email_idx].strip()
                if (email_idx != -1 and len(row) > email_idx)
                else None
            )
            try:
                recipients.append(
                    RecipientRequest(name=name_val, email=email_val or None)
                )
            except Exception:
                continue

    elif ext in [".xlsx", ".xls"]:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            sheet = wb.active
            if sheet is None:
                raise ValueError("No active worksheet found in Excel file.")
            sheet_rows = list(sheet.iter_rows(values_only=True))
            if not sheet_rows:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Excel spreadsheet is empty.",
                )
            name_col = -1
            email_col = -1
            header_row_idx = 0
            for r_idx, row in enumerate(sheet_rows):
                for c_idx, val in enumerate(row):
                    if val is None:
                        continue
                    v_str = str(val).strip().lower()
                    if v_str in [
                        "name",
                        "recipient_name",
                        "full name",
                        "fullname",
                        "recipient",
                    ]:
                        name_col = c_idx
                        header_row_idx = r_idx
                    elif v_str in ["email", "recipient_email", "mail", "e-mail"]:
                        email_col = c_idx

                if name_col != -1:
                    break

            start_r = header_row_idx + 1 if name_col != -1 else 0
            if name_col == -1:
                name_col = 0
                email_col = 1 if len(sheet_rows[0]) > 1 else -1

            for row in sheet_rows[start_r:]:
                if not row or len(row) <= name_col:
                    continue
                raw_name = row[name_col]
                if raw_name is None:
                    continue
                name_val = str(raw_name).strip()
                if not name_val:
                    continue
                raw_email = (
                    row[email_col]
                    if (email_col != -1 and len(row) > email_col)
                    else None
                )
                email_val = str(raw_email).strip() if raw_email is not None else None
                try:
                    recipients.append(
                        RecipientRequest(name=name_val, email=email_val or None)
                    )
                except Exception:
                    continue
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error reading Excel file: {e}",
            ) from e
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported format '{ext}'. "
                "Please upload a .json, .csv, or .xlsx file."
            ),
        )

    if not recipients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No valid recipient records found in '{filename}'. "
                "Ensure there is a 'name' column or field."
            ),
        )

    if len(recipients) > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Batch size of {len(recipients)} exceeds "
                "maximum allowed limit of 1000 recipients."
            ),
        )

    return recipients


@router.post(
    "/api/recipients/parse-file/",
    response_model=ParseRecipientsResponse,
    status_code=status.HTTP_200_OK,
    summary="Parse recipients from JSON, CSV, or Excel file",
    description="Upload a .json, .csv, or .xlsx file to extract recipients.",
)
async def parse_recipients_file(
    file: UploadFile = File(...),
) -> ParseRecipientsResponse:
    """Parse recipient records from uploaded JSON, CSV, or Excel file."""
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    filename = file.filename or "uploaded_file"
    recipients = parse_recipients_from_bytes(filename, content)
    return ParseRecipientsResponse(
        recipients=recipients,
        total_count=len(recipients),
        filename=filename,
    )


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
) -> Response:
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

    storage = service.storage

    if isinstance(storage, LocalStorageBackend):
        settings = get_settings()
        file_path = Path(cert.file_path).resolve()
        base_storage = Path(settings.output_dir).resolve()
        try:
            file_path.relative_to(base_storage)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Access denied: file path is outside authorized storage directory"
                ),
            ) from None

    if not storage.exists(cert.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate PDF file is missing from storage",
        )

    safe_name = sanitize_filename(cert.recipient_name)
    download_filename = f"certificate_{safe_name}.pdf"

    if isinstance(storage, LocalStorageBackend):
        return FileResponse(
            path=str(cert.file_path),
            media_type="application/pdf",
            filename=download_filename,
        )

    return StreamingResponse(
        storage.stream(cert.file_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
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


@router.delete(
    "/api/jobs/cleanup/empty/",
    status_code=status.HTTP_200_OK,
    summary="Delete all empty jobs",
    description="Deletes all jobs that have zero certificates or zero recipients.",
)
def delete_empty_jobs(
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Delete all empty jobs with zero certificates."""
    service = JobService(db)
    return service.delete_empty_jobs()


@router.delete(
    "/api/jobs/{job_id}/",
    status_code=status.HTTP_200_OK,
    summary="Delete a batch job and all its certificates",
    description=(
        "Deletes the job and cleans up all generated certificate files from storage."
    ),
)
def delete_job(
    job_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Delete a batch job and all associated certificates."""
    service = JobService(db)
    deleted = service.delete_job(job_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return {
        "status": "success",
        "message": f"Job '{job_id}' and all its certificates deleted successfully",
        "job_id": job_id,
    }


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


@router.post(
    "/api/certificates/download-selected-zip/",
    summary="Download selected certificates as a ZIP archive",
    description="Packages selected certificates by IDs into a single ZIP archive.",
)
def download_selected_certificates_zip(
    payload: DownloadSelectedZipRequest,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download a ZIP archive containing explicitly selected certificate IDs."""
    service = JobService(db)
    try:
        zip_path = service.create_certificates_zip(payload.certificate_ids)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from None

    zip_filename = f"selected_certificates_{len(payload.certificate_ids)}.zip"
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
) -> Response:
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

    storage = service.storage

    if isinstance(storage, LocalStorageBackend):
        settings = get_settings()
        file_path = Path(cert.file_path).resolve()
        base_storage = Path(settings.output_dir).resolve()
        try:
            file_path.relative_to(base_storage)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Access denied: file path is outside authorized storage directory"
                ),
            ) from None

    if not storage.exists(cert.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate PDF file is missing from storage",
        )

    if isinstance(storage, LocalStorageBackend):
        return FileResponse(
            path=str(cert.file_path),
            media_type="application/pdf",
            headers={"Content-Disposition": "inline"},
        )

    return StreamingResponse(
        storage.stream(cert.file_path),
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
