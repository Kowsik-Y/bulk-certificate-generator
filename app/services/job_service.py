"""Service layer handling business logic for certificate jobs."""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.generator.certificate_generator import (
    generate_certificate,
    generate_certificate_bytes,
)
from app.models import Certificate, Job, utc_now
from app.repositories.job_repository import JobRepository
from app.schemas import (
    CertificateFileItemResponse,
    CertificateListResponse,
    JobCreateRequest,
    SystemStatsResponse,
)
from app.storage import StorageBackend, create_storage_backend
from app.websockets import publish_job_event

logger = logging.getLogger(__name__)


def format_bytes(size: int) -> str:
    """Format bytes into human-readable string (KB, MB, GB)."""
    f_size = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if f_size < 1024.0:
            return f"{f_size:.1f} {unit}"
        f_size /= 1024.0
    return f"{f_size:.1f} TB"


class JobService:
    """Orchestrates job lifecycle, certificate generation, and status retrieval."""

    def __init__(self, db: Session, storage: StorageBackend | None = None) -> None:
        self.db = db
        self.repo = JobRepository(db)
        self.settings = get_settings()
        self.storage = storage or create_storage_backend(self.settings)

    def create_job(self, request: JobCreateRequest) -> Job:
        """Create a job and all associated certificate records in pending state.

        Args:
            request: Validated job creation request.

        Returns:
            The created Job instance.
        """
        job = self.repo.create_job(
            title=request.title,
            organization=request.organization,
            date_of_issue=request.date_of_issue,
            total_recipients=len(request.recipients),
            signature_data=request.signature_data,
            template=getattr(request, "template", "classic") or "classic",
        )

        for recipient in request.recipients:
            self.repo.create_certificate(
                job_id=job.id,
                recipient_name=recipient.name,
                recipient_email=recipient.email,
            )

        self.db.commit()
        self.db.refresh(job)

        publish_job_event(
            self.settings.redis_url,
            {
                "type": "job_created",
                "job_id": job.id,
                "title": job.title,
                "total_recipients": job.total_recipients,
            },
        )
        return job

    def update_job_task_id(self, job_id: str, task_id: str) -> None:
        """Record the Celery task ID for background tracking."""
        job = self.repo.get_job_by_id(job_id)
        if job:
            self.repo.update_job(job, celery_task_id=task_id)
            self.db.commit()

    def process_job(self, job_id: str) -> Job:
        """Process certificate generation for all recipients in a job.

        Implements per-certificate error isolation: if a certificate fails
        (e.g., corrupt font, invalid data), the error is logged and stored,
        and processing continues for all remaining recipients.

        Args:
            job_id: ID of the job to process.

        Returns:
            The updated Job instance.

        Raises:
            ValueError: If the job ID is not found.
        """
        job = self.repo.get_job_by_id(job_id)
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found")

        # Mark job as processing
        self.repo.update_job(job, status="processing")
        self.db.commit()

        publish_job_event(
            self.settings.redis_url,
            {
                "event": "job_started",
                "type": "job_started",
                "job_id": job.id,
                "title": job.title,
                "total": job.total_recipients,
                "total_recipients": job.total_recipients,
                "processed": 0,
                "current": 0,
                "percent": 0,
                "percentage": 0,
            },
        )

        # Decode signature image if provided
        signature_bytes: bytes | None = None
        if job.signature_data:
            try:
                import base64

                raw_b64 = job.signature_data
                if "," in raw_b64:
                    raw_b64 = raw_b64.split(",", 1)[1]
                signature_bytes = base64.b64decode(raw_b64)
            except Exception as e:
                logger.warning("Failed to decode signature image base64: %s", e)

        success_count = 0
        fail_count = 0

        backend_name = (self.settings.storage_backend or "local").lower()
        is_s3 = backend_name in ("s3", "rustfs", "minio")
        output_dir = Path(self.settings.output_dir)
        if not is_s3:
            output_dir.mkdir(parents=True, exist_ok=True)

        total_certs = len(job.certificates)
        template_name = getattr(job, "template", "classic") or "classic"
        max_workers = max(1, min(self.settings.max_parallel_workers, 20))

        def _process_single_cert(
            cert_id: str, recipient_name: str
        ) -> tuple[str, str, str | None, str | None]:
            """Generate and upload a single certificate in worker thread."""
            try:
                if is_s3:
                    storage_key = f"{job.id}/{cert_id}.pdf"
                    pdf_bytes = generate_certificate_bytes(
                        recipient_name=recipient_name,
                        title=job.title,
                        organization=job.organization,
                        date_of_issue=job.date_of_issue,
                        signature_image_bytes=signature_bytes,
                        template=template_name,
                    )
                    stored_path = self.storage.upload(
                        key=storage_key,
                        data=pdf_bytes,
                        content_type="application/pdf",
                    )
                else:
                    output_file = output_dir / f"{cert_id}.pdf"
                    generate_certificate(
                        recipient_name=recipient_name,
                        title=job.title,
                        organization=job.organization,
                        date_of_issue=job.date_of_issue,
                        output_path=str(output_file),
                        signature_image_bytes=signature_bytes,
                        template=template_name,
                    )
                    stored_path = str(output_file)
                return (cert_id, "success", stored_path, None)
            except Exception as exc:
                logger.exception("Failed to generate certificate %s", cert_id)
                return (cert_id, "failed", None, str(exc))

        certs_to_generate: list[Certificate] = []
        for cert in job.certificates:
            # Idempotency check: skip regeneration if certificate was already created
            if (
                cert.status == "success"
                and cert.file_path
                and self.storage.exists(cert.file_path)
            ):
                success_count += 1
            else:
                certs_to_generate.append(cert)

        from concurrent.futures import ThreadPoolExecutor, as_completed

        processed_so_far = success_count
        if certs_to_generate:
            cert_map = {c.id: c for c in certs_to_generate}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_id = {
                    executor.submit(_process_single_cert, c.id, c.recipient_name): c.id
                    for c in certs_to_generate
                }

                for future in as_completed(future_to_id):
                    c_id = future_to_id[future]
                    target_cert = cert_map[c_id]
                    processed_so_far += 1

                    try:
                        _, status, stored_path, error_msg = future.result()
                    except Exception as err:
                        status, stored_path, error_msg = "failed", None, str(err)

                    if status == "success":
                        success_count += 1
                        self.repo.update_certificate(
                            target_cert,
                            status="success",
                            file_path=stored_path,
                            error_message=None,
                        )
                    else:
                        fail_count += 1
                        self.repo.update_certificate(
                            target_cert,
                            status="failed",
                            file_path=None,
                            error_message=error_msg,
                        )

                    self.db.commit()

                    # Broadcast progress
                    pct = (
                        round((processed_so_far / total_certs) * 100)
                        if total_certs
                        else 100
                    )
                    publish_job_event(
                        self.settings.redis_url,
                        {
                            "event": "job_progress",
                            "type": "job_progress",
                            "job_id": job.id,
                            "title": job.title,
                            "recipient_name": target_cert.recipient_name,
                            "current_recipient": target_cert.recipient_name,
                            "processed": processed_so_far,
                            "current": processed_so_far,
                            "total": total_certs,
                            "total_recipients": total_certs,
                            "percent": pct,
                            "percentage": pct,
                            "cert_status": target_cert.status,
                        },
                    )

        # Determine terminal status
        final_status = "completed" if fail_count == 0 else "completed_with_errors"

        self.repo.update_job(
            job,
            status=final_status,
            successful_count=success_count,
            failed_count=fail_count,
            completed_at=utc_now(),
        )
        self.db.commit()
        self.db.refresh(job)

        publish_job_event(
            self.settings.redis_url,
            {
                "event": "job_completed",
                "type": "job_completed",
                "job_id": job.id,
                "title": job.title,
                "status": final_status,
                "total": total_certs,
                "processed": total_certs,
                "percent": 100,
                "percentage": 100,
                "successful_count": success_count,
                "failed_count": fail_count,
            },
        )
        return job

    def get_job_status(self, job_id: str) -> Job | None:
        """Retrieve job status information by ID."""
        return self.repo.get_job_by_id(job_id)

    def get_certificates(self, job_id: str) -> list[Certificate]:
        """Retrieve all certificate records for a job."""
        return self.repo.get_certificates_by_job_id(job_id)

    def get_certificate_by_id(self, cert_id: str) -> Certificate | None:
        """Retrieve a single certificate by ID."""
        return self.repo.get_certificate_by_id(cert_id)

    def list_jobs(self, skip: int = 0, limit: int = 50) -> list[Job]:
        """List all jobs with pagination."""
        return self.repo.list_all_jobs(skip=skip, limit=limit)

    def list_certificate_files(
        self,
        job_id: str | None = None,
        status: str | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> CertificateListResponse:
        """Retrieve paginated certificates enriched with filesystem metadata."""
        items, total = self.repo.list_all_certificates(
            job_id=job_id,
            status=status,
            search=search,
            skip=skip,
            limit=limit,
        )

        backend_name = (self.settings.storage_backend or "local").lower()
        file_items: list[CertificateFileItemResponse] = []
        for cert in items:
            file_size: int | None = None
            file_exists = False
            presigned_url: str | None = None
            if cert.file_path:
                file_exists = self.storage.exists(cert.file_path)
                if file_exists:
                    file_size = self.storage.get_size(cert.file_path)
                    presigned_url = self.storage.get_presigned_url(cert.file_path)

            file_items.append(
                CertificateFileItemResponse(
                    id=cert.id,
                    job_id=cert.job_id,
                    job_title=cert.job.title if cert.job else "Unknown",
                    job_organization=(cert.job.organization if cert.job else "Unknown"),
                    recipient_name=cert.recipient_name,
                    recipient_email=cert.recipient_email,
                    status=cert.status,
                    file_size_bytes=file_size,
                    file_size_formatted=(
                        format_bytes(file_size) if file_size is not None else None
                    ),
                    error_message=cert.error_message,
                    file_exists=file_exists,
                    created_at=cert.created_at,
                    download_url=f"/api/certificates/{cert.id}/download/",
                    preview_url=f"/api/certificates/{cert.id}/preview/",
                    presigned_url=presigned_url,
                    storage_backend=backend_name,
                    template=(
                        cert.job.template
                        if (cert.job and getattr(cert.job, "template", None))
                        else "classic"
                    ),
                )
            )

        return CertificateListResponse(
            total=total,
            skip=skip,
            limit=limit,
            items=file_items,
        )

    def delete_certificate(self, cert_id: str) -> bool:
        """Delete an individual certificate and remove its stored file safely."""
        cert = self.repo.get_certificate_by_id(cert_id)
        if not cert:
            return False

        if cert.file_path:
            self.storage.delete(cert.file_path)

        # Update parent job counters if job exists
        if cert.job:
            if cert.status == "success" and cert.job.successful_count > 0:
                cert.job.successful_count -= 1
            elif cert.status == "failed" and cert.job.failed_count > 0:
                cert.job.failed_count -= 1
            if cert.job.total_recipients > 0:
                cert.job.total_recipients -= 1

        self.repo.delete_certificate(cert)
        self.db.commit()
        return True

    def create_job_zip(self, job_id: str) -> Path:
        """Create a zip archive containing all generated certificates for a job."""
        import zipfile

        job = self.repo.get_job_by_id(job_id)
        if not job:
            raise ValueError(f"Job '{job_id}' not found")

        successful_certs = [
            c for c in job.certificates if c.status == "success" and c.file_path
        ]
        if not successful_certs:
            raise ValueError(
                "No generated certificates available to download in this job"
            )

        import tempfile

        zip_dir = Path(tempfile.gettempdir()) / "cert_zips"
        zip_dir.mkdir(parents=True, exist_ok=True)
        zip_path = zip_dir / f"certificates_job_{job.id}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            name_counts: dict[str, int] = {}
            for cert in successful_certs:
                if not cert.file_path or not self.storage.exists(cert.file_path):
                    continue

                clean = (
                    "".join(
                        c
                        for c in cert.recipient_name
                        if c.isalnum() or c in (" ", "-", "_")
                    )
                    .strip()
                    .replace(" ", "_")
                )
                safe_name = clean or "certificate"

                count = name_counts.get(safe_name, 0)
                name_counts[safe_name] = count + 1
                arc_name = (
                    f"{safe_name}.pdf" if count == 0 else f"{safe_name}_{count}.pdf"
                )

                try:
                    pdf_bytes = self.storage.get_bytes(cert.file_path)
                    zf.writestr(arc_name, pdf_bytes)
                except Exception:
                    logger.warning(
                        "Failed to read %s for zip packaging", cert.file_path
                    )

        return zip_path

    def create_certificates_zip(self, cert_ids: list[str]) -> Path:
        """Create a zip archive containing selected certificates by ID."""
        import uuid
        import zipfile

        certs = [self.repo.get_certificate_by_id(cid) for cid in cert_ids]
        valid_certs = [c for c in certs if c and c.status == "success" and c.file_path]
        if not valid_certs:
            raise ValueError(
                "No ready certificates available for download in the selected list"
            )

        import tempfile

        zip_dir = Path(tempfile.gettempdir()) / "cert_zips"
        zip_dir.mkdir(parents=True, exist_ok=True)
        zip_path = zip_dir / f"selected_certificates_{uuid.uuid4().hex[:8]}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            name_counts: dict[str, int] = {}
            for cert in valid_certs:
                if not cert.file_path or not self.storage.exists(cert.file_path):
                    continue

                clean = (
                    "".join(
                        c
                        for c in cert.recipient_name
                        if c.isalnum() or c in (" ", "-", "_")
                    )
                    .strip()
                    .replace(" ", "_")
                )
                safe_name = clean or "certificate"
                count = name_counts.get(safe_name, 0)
                name_counts[safe_name] = count + 1
                arc_name = (
                    f"{safe_name}.pdf" if count == 0 else f"{safe_name}_{count}.pdf"
                )

                try:
                    pdf_bytes = self.storage.get_bytes(cert.file_path)
                    zf.writestr(arc_name, pdf_bytes)
                except Exception as exc:
                    logger.warning(
                        "Failed to read %s for zip packaging: %s",
                        cert.file_path,
                        exc,
                    )

        return zip_path

    def get_system_stats(self) -> SystemStatsResponse:
        """Aggregate total job/certificate metrics and calculate storage usage."""
        db_stats = self.repo.get_system_stats()
        storage_stats = self.storage.get_stats()
        total_bytes = storage_stats.get("total_bytes", 0)
        backend_name = (self.settings.storage_backend or "local").lower()
        bucket = (
            self.settings.s3_bucket_name
            if backend_name in ("s3", "rustfs", "minio")
            else None
        )

        return SystemStatsResponse(
            total_jobs=db_stats["total_jobs"],
            total_certificates=db_stats["total_certificates"],
            successful_certificates=db_stats["successful_certificates"],
            failed_certificates=db_stats["failed_certificates"],
            total_storage_bytes=total_bytes,
            total_storage_formatted=format_bytes(total_bytes),
            storage_backend=backend_name,
            bucket_name=bucket,
        )
