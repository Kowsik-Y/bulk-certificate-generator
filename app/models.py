"""SQLAlchemy ORM models for jobs and certificates."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    """Return current UTC datetime stripped of tzinfo for SQLite."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Job(Base):
    """Represents a bulk certificate generation job."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")

    # Status lifecycle: pending -> processing -> completed / completed_with_errors
    total_recipients: Mapped[int] = mapped_column(Integer, nullable=False)
    successful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Event/course metadata
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    organization: Mapped[str] = mapped_column(String(300), nullable=False)
    date_of_issue: Mapped[str] = mapped_column(String(10), nullable=False)

    # Celery task tracking
    celery_task_id: Mapped[str | None] = mapped_column(String, nullable=True)

    certificates: Mapped[list["Certificate"]] = relationship(
        "Certificate",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="Certificate.created_at",
    )


class Certificate(Base):
    """Represents an individual certificate generated within a job."""

    __tablename__ = "certificates"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), nullable=False)

    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # Status lifecycle: pending -> success / failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    job: Mapped[Job] = relationship("Job", back_populates="certificates")
