from unittest.mock import MagicMock

import pytest

from app.tasks import process_job_task


def test_process_job_task_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """process_job_task successfully executes and returns status dict."""
    mock_service = MagicMock()
    monkeypatch.setattr("app.tasks.JobService", lambda db: mock_service)
    monkeypatch.setattr("app.tasks.SessionLocal", MagicMock())

    result = process_job_task("test-job-id")
    assert result == {"job_id": "test-job-id", "status": "completed"}
    mock_service.process_job.assert_called_once_with("test-job-id")


def test_process_job_task_retry_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """process_job_task catches unexpected error, rolls back DB and calls retry."""
    mock_db = MagicMock()
    mock_service = MagicMock()
    mock_service.process_job.side_effect = RuntimeError("DB connection dropped")

    monkeypatch.setattr("app.tasks.JobService", lambda db: mock_service)
    monkeypatch.setattr("app.tasks.SessionLocal", lambda: mock_db)

    # In eager mode with exc passed to retry(), Celery re-raises the exception
    with pytest.raises(RuntimeError, match="DB connection dropped"):
        process_job_task("failing-job-id")

    mock_db.rollback.assert_called_once()
    mock_db.close.assert_called_once()
