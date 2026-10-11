"""Integration tests for FastAPI endpoints."""

from fastapi.testclient import TestClient


def test_health_and_root_endpoints(client: TestClient) -> None:
    """Verify health and root index endpoints return 200 OK."""
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"

    root_resp = client.get("/")
    assert root_resp.status_code == 200
    assert "documentation" in root_resp.json()


def test_create_job_returns_202_with_job_id(client: TestClient) -> None:
    """POST /api/jobs/ with valid data returns 202 Accepted and job_id."""
    payload = {
        "title": "FastAPI Certification",
        "organization": "PyAcademy",
        "date_of_issue": "2026-10-15",
        "recipients": [
            {"name": "Alice Johnson", "email": "alice@example.com"},
            {"name": "Bob Smith", "email": "bob@example.com"},
            {"name": "Charlie Day"},
        ],
    }

    response = client.post("/api/jobs/", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] in ("pending", "completed")
    assert "3 certificates" in data["message"]


def test_get_job_status_returns_correct_progress(client: TestClient) -> None:
    """GET /api/jobs/{id}/ returns full job status and recipient counts."""
    payload = {
        "title": "Machine Learning Bootcamp",
        "organization": "AI Guild",
        "date_of_issue": "2026-10-15",
        "recipients": [
            {"name": "Alice Brown", "email": "alice@example.com"},
            {"name": "Bob Green", "email": "bob@example.com"},
        ],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    status_resp = client.get(f"/api/jobs/{job_id}/")
    assert status_resp.status_code == 200
    job_data = status_resp.json()
    assert job_data["id"] == job_id
    assert job_data["title"] == "Machine Learning Bootcamp"
    assert job_data["organization"] == "AI Guild"
    assert job_data["total_recipients"] == 2
    assert job_data["successful_count"] == 2
    assert job_data["failed_count"] == 0
    assert job_data["status"] == "completed"
    assert job_data["completed_at"] is not None


def test_get_certificates_returns_list(client: TestClient) -> None:
    """GET /api/jobs/{id}/certificates/ returns list of certificates for the job."""
    payload = {
        "title": "Python Specialist",
        "organization": "Dev Institute",
        "date_of_issue": "2026-10-15",
        "recipients": [
            {"name": "Diana Prince", "email": "diana@themyscira.com"},
            {"name": "Clark Kent"},
        ],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    certs_resp = client.get(f"/api/jobs/{job_id}/certificates/")
    assert certs_resp.status_code == 200
    certs = certs_resp.json()
    assert len(certs) == 2
    names = {c["recipient_name"] for c in certs}
    assert names == {"Diana Prince", "Clark Kent"}
    assert all(c["status"] == "success" for c in certs)
    assert all(c["file_path"] is not None for c in certs)


def test_download_certificate_returns_pdf(client: TestClient) -> None:
    """GET /api/certificates/{id}/download/ returns the generated PDF file."""
    payload = {
        "title": "Docker Masterclass",
        "organization": "Cloud Academy",
        "date_of_issue": "2026-10-15",
        "recipients": [{"name": "Bruce Wayne", "email": "bruce@wayne.corp"}],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    certs_resp = client.get(f"/api/jobs/{job_id}/certificates/")
    cert_id = certs_resp.json()[0]["id"]

    download_resp = client.get(f"/api/certificates/{cert_id}/download/")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/pdf"
    assert "Bruce_Wayne" in download_resp.headers.get("content-disposition", "")
    assert download_resp.content.startswith(b"%PDF")


def test_get_nonexistent_job_returns_404(client: TestClient) -> None:
    """GET /api/jobs/unknown-id returns 404 Not Found."""
    resp = client.get("/api/jobs/non-existent-uuid/")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_certificates_for_nonexistent_job_returns_404(client: TestClient) -> None:
    """GET /api/jobs/unknown-id/certificates/ returns 404 Not Found."""
    resp = client.get("/api/jobs/non-existent-uuid/certificates/")
    assert resp.status_code == 404


def test_download_nonexistent_certificate_returns_404(client: TestClient) -> None:
    """GET /api/certificates/unknown-id/download/ returns 404 Not Found."""
    resp = client.get("/api/certificates/unknown-id/download/")
    assert resp.status_code == 404


def test_download_failed_certificate_returns_400(
    client: TestClient, db_session
) -> None:
    """GET /api/certificates/{id}/download/ returns 400 if cert failed."""
    from app.models import Certificate, Job

    job = Job(
        title="Test Job",
        organization="Test Org",
        date_of_issue="2026-10-15",
        total_recipients=1,
    )
    db_session.add(job)
    db_session.flush()

    cert = Certificate(
        job_id=job.id,
        recipient_name="Failed User",
        status="failed",
        error_message="Simulation error",
        file_path=None,
    )
    db_session.add(cert)
    db_session.commit()

    resp = client.get(f"/api/certificates/{cert.id}/download/")
    assert resp.status_code == 400
    assert "not available" in resp.json()["detail"].lower()


def test_download_missing_file_from_storage_returns_404(
    client: TestClient, db_session, temp_output_dir
) -> None:
    """GET /api/certificates/{id}/download/ returns 404 if file is deleted."""
    from app.models import Certificate, Job

    job = Job(
        title="Test Job",
        organization="Test Org",
        date_of_issue="2026-10-15",
        total_recipients=1,
    )
    db_session.add(job)
    db_session.flush()

    cert = Certificate(
        job_id=job.id,
        recipient_name="Missing File User",
        status="success",
        file_path=str(temp_output_dir / "non_existent_path_xyz_123.pdf"),
    )
    db_session.add(cert)
    db_session.commit()

    resp = client.get(f"/api/certificates/{cert.id}/download/")
    assert resp.status_code == 404
    assert "missing from storage" in resp.json()["detail"].lower()


def test_download_path_traversal_returns_403(client: TestClient, db_session) -> None:
    """GET /api/certificates/{id}/download/ returns 403 if path is outside storage."""
    from app.models import Certificate, Job

    job = Job(
        title="Test Job",
        organization="Test Org",
        date_of_issue="2026-10-15",
        total_recipients=1,
    )
    db_session.add(job)
    db_session.flush()

    cert = Certificate(
        job_id=job.id,
        recipient_name="Malicious User",
        status="success",
        file_path="/etc/passwd",
    )
    db_session.add(cert)
    db_session.commit()

    resp = client.get(f"/api/certificates/{cert.id}/download/")
    assert resp.status_code == 403
    assert "outside authorized storage" in resp.json()["detail"].lower()


def test_database_init_and_get_db() -> None:
    """Test database init_db and get_db session generator."""
    from app.database import get_db, init_db

    init_db()
    gen = get_db()
    session = next(gen)
    assert session is not None
    try:
        next(gen)
    except StopIteration:
        pass
