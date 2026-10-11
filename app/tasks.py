"""Celery background tasks for certificate generation."""

import logging
from typing import Any

from app.celery_app import celery_app
from app.database import SessionLocal
from app.services.job_service import JobService

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    name="app.tasks.process_job_task",
)
def process_job_task(self: Any, job_id: str) -> dict[str, str]:
    """Background task to generate all certificates for a submitted job.

    Per-certificate errors are captured inside JobService and do not fail
    the entire task. If an infrastructure exception occurs (e.g. database disconnect),
    the task will retry with exponential backoff.

    Args:
        job_id: Unique UUID string identifying the generation job.

    Returns:
        Summary dict containing job_id and status.
    """
    logger.info("Starting background processing for job %s", job_id)
    db = SessionLocal()
    try:
        service = JobService(db)
        service.process_job(job_id)
        logger.info("Successfully finished processing job %s", job_id)
        return {"job_id": job_id, "status": "completed"}
    except Exception as exc:
        db.rollback()
        logger.exception("Job %s encountered unexpected failure", job_id)
        retry_delay = 60 * (2**self.request.retries)
        raise self.retry(exc=exc, countdown=retry_delay) from exc

    finally:
        db.close()
