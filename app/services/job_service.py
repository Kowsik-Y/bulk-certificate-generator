"""Service layer handling business logic for certificate jobs."""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.generator.certificate_generator import generate_certificate
from app.models import Certificate, Job, utc_now
from app.repositories.job_repository import JobRepository
from app.schemas import JobCreateRequest

logger = logging.getLogger(__name__)


class JobService:
    """Orchestrates job lifecycle, certificate generation, and status retrieval."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = JobRepository(db)
        self.settings = get_settings()

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
        )

        for recipient in request.recipients:
            self.repo.create_certificate(
                job_id=job.id,
                recipient_name=recipient.name,
                recipient_email=recipient.email,
            )

        self.db.commit()
        self.db.refresh(job)
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

        success_count = 0
        fail_count = 0

        # Ensure output directory exists
        output_dir = Path(self.settings.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for cert in job.certificates:
            output_file = output_dir / f"{cert.id}.pdf"
            try:
                generate_certificate(
                    recipient_name=cert.recipient_name,
                    title=job.title,
                    organization=job.organization,
                    date_of_issue=job.date_of_issue,
                    output_path=str(output_file),
                )
                self.repo.update_certificate(
                    cert,
                    status="success",
                    file_path=str(output_file),
                    error_message=None,
                )
                success_count += 1
            except Exception as exc:
                logger.exception("Failed to generate certificate %s", cert.id)
                self.repo.update_certificate(
                    cert,
                    status="failed",
                    file_path=None,
                    error_message=str(exc),
                )
                fail_count += 1

            self.db.commit()

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
