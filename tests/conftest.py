"""Shared pytest fixtures for Bulk Certificate Generator test suite."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.celery_app import celery_app
from app.config import Settings
from app.database import Base, get_db
from app.main import app

# Shared in-memory SQLite database across connections
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session", autouse=True)
def configure_celery_test_mode() -> None:
    """Configure Celery to run synchronously in eager mode for all tests."""
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )


@pytest.fixture
def test_engine():
    """Create a fresh SQLite in-memory engine for each test."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    """Provide a dedicated SQLAlchemy session connected to the test database."""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
        expire_on_commit=False,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def temp_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a temporary directory for generated PDF files during tests."""
    out_dir = tmp_path / "test_output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Override settings output_dir
    def mock_get_settings() -> Settings:
        return Settings(
            output_dir=str(out_dir),
            database_url=TEST_DATABASE_URL,
        )

    monkeypatch.setattr("app.config.get_settings", mock_get_settings)
    monkeypatch.setattr("app.services.job_service.get_settings", mock_get_settings)
    monkeypatch.setattr("app.routers.jobs.get_settings", mock_get_settings)
    return out_dir


@pytest.fixture
def client(
    db_session: Session,
    temp_output_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with DB session override, eager Celery, and temp storage."""

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Also make sure the background tasks use this session or eager mode
    monkeypatch.setattr(
        "app.tasks.SessionLocal",
        lambda: db_session,
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
