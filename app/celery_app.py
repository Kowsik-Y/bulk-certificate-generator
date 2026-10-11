"""Celery application instance and configuration."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "certificate_generator",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,  # Acknowledge only after task execution finishes
    worker_prefetch_multiplier=1,  # Fair task distribution across workers
    task_reject_on_worker_lost=True,  # Re-enqueue if worker process is abruptly lost
)
