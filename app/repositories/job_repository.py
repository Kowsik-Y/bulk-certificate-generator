"""Data access repository for Job and Certificate entities."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Certificate, Job


class JobRepository:
    """Repository managing persistence for jobs and certificates."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_job(
        self,
        title: str,
        organization: str,
        date_of_issue: str,
        total_recipients: int,
        job_id: str | None = None,
        signature_data: str | None = None,
    ) -> Job:
        """Create and add a new Job record."""
        job_kwargs: dict[str, Any] = {
            "title": title,
            "organization": organization,
            "date_of_issue": date_of_issue,
            "total_recipients": total_recipients,
            "signature_data": signature_data,
            "status": "pending",
            "successful_count": 0,
            "failed_count": 0,
        }
        if job_id:
            job_kwargs["id"] = job_id
        job = Job(**job_kwargs)
        self.db.add(job)
        self.db.flush()
        return job

    def create_certificate(
        self,
        job_id: str,
        recipient_name: str,
        recipient_email: str | None = None,
        cert_id: str | None = None,
    ) -> Certificate:
        """Create and add a new Certificate record."""
        cert_kwargs: dict[str, Any] = {
            "job_id": job_id,
            "recipient_name": recipient_name,
            "recipient_email": recipient_email,
            "status": "pending",
        }
        if cert_id:
            cert_kwargs["id"] = cert_id
        cert = Certificate(**cert_kwargs)
        self.db.add(cert)
        self.db.flush()
        return cert

    def get_job_by_id(self, job_id: str) -> Job | None:
        """Retrieve a job by ID, eagerly loading its certificates."""
        stmt = (
            select(Job).options(selectinload(Job.certificates)).where(Job.id == job_id)
        )
        return self.db.scalars(stmt).first()

    def update_job(self, job: Job, **kwargs: Any) -> Job:
        """Update fields on a Job instance."""
        for field, value in kwargs.items():
            if hasattr(job, field):
                setattr(job, field, value)
        self.db.flush()
        return job

    def update_certificate(self, cert: Certificate, **kwargs: Any) -> Certificate:
        """Update fields on a Certificate instance."""
        for field, value in kwargs.items():
            if hasattr(cert, field):
                setattr(cert, field, value)
        self.db.flush()
        return cert

    def get_certificates_by_job_id(self, job_id: str) -> list[Certificate]:
        """Retrieve all certificate records associated with a job ID."""
        stmt = (
            select(Certificate)
            .where(Certificate.job_id == job_id)
            .order_by(Certificate.created_at)
        )
        return list(self.db.scalars(stmt).all())

    def get_certificate_by_id(self, cert_id: str) -> Certificate | None:
        """Retrieve a specific certificate by its ID, eagerly loading its job."""
        stmt = (
            select(Certificate)
            .options(selectinload(Certificate.job))
            .where(Certificate.id == cert_id)
        )
        return self.db.scalars(stmt).first()

    def list_all_jobs(self, skip: int = 0, limit: int = 50) -> list[Job]:
        """List jobs ordered by creation date descending."""
        stmt = select(Job).order_by(Job.created_at.desc()).offset(skip).limit(limit)
        return list(self.db.scalars(stmt).all())

    def list_all_certificates(
        self,
        job_id: str | None = None,
        status: str | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Certificate], int]:
        """Query certificate files with optional filtering and pagination."""
        stmt = select(Certificate).options(selectinload(Certificate.job))

        if job_id:
            stmt = stmt.where(Certificate.job_id == job_id)
        if status:
            stmt = stmt.where(Certificate.status == status)
        if search:
            search_pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                (Certificate.recipient_name.ilike(search_pattern))
                | (Certificate.recipient_email.ilike(search_pattern))
            )

        # Get total matching count
        from sqlalchemy import func

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        # Apply ordering and pagination
        stmt = stmt.order_by(Certificate.created_at.desc()).offset(skip).limit(limit)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def delete_certificate(self, cert: Certificate) -> None:
        """Remove a certificate record from the database."""
        self.db.delete(cert)
        self.db.flush()

    def get_system_stats(self) -> dict[str, int]:
        """Compute aggregated statistics for jobs and certificates."""
        from sqlalchemy import func

        total_jobs = self.db.scalar(select(func.count(Job.id))) or 0
        total_certs = self.db.scalar(select(func.count(Certificate.id))) or 0
        successful_certs = (
            self.db.scalar(
                select(func.count(Certificate.id)).where(
                    Certificate.status == "success"
                )
            )
            or 0
        )
        failed_certs = (
            self.db.scalar(
                select(func.count(Certificate.id)).where(Certificate.status == "failed")
            )
            or 0
        )

        return {
            "total_jobs": total_jobs,
            "total_certificates": total_certs,
            "successful_certificates": successful_certs,
            "failed_certificates": failed_certs,
        }
