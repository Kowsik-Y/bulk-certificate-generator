"""Integration tests for FastAPI endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient


def test_health_and_root_endpoints(client: TestClient) -> None:
    """Verify health and root index endpoints return 200 OK."""
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"

    root_resp = client.get("/")
    assert root_resp.status_code == 200
    assert "text/html" in root_resp.headers["content-type"]


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


def test_dashboard_ui_served(client: TestClient) -> None:
    """GET / and GET /manager return the HTML dashboard."""
    r1 = client.get("/")
    assert r1.status_code == 200
    assert "text/html" in r1.headers["content-type"]
    assert "CertManager" in r1.text

    r2 = client.get("/manager")
    assert r2.status_code == 200
    assert "CertManager" in r2.text

    r3 = client.get("/api/info")
    assert r3.status_code == 200
    assert "dashboard" in r3.json()


def test_list_jobs_and_stats(client: TestClient) -> None:
    """GET /api/jobs/ and GET /api/stats/ return expected structure."""
    client.post(
        "/api/jobs/",
        json={
            "title": "Cloud Architecture",
            "organization": "Cloud Org",
            "date_of_issue": "2026-10-15",
            "recipients": [{"name": "Neo", "email": "neo@matrix.org"}],
        },
    )
    jobs_resp = client.get("/api/jobs/")
    assert jobs_resp.status_code == 200
    assert len(jobs_resp.json()) >= 1

    stats_resp = client.get("/api/stats/")
    assert stats_resp.status_code == 200
    data = stats_resp.json()
    assert data["total_jobs"] >= 1
    assert data["total_certificates"] >= 1
    assert "total_storage_formatted" in data


def test_list_certificates_with_filtering(client: TestClient) -> None:
    """GET /api/certificates/ filters by query and status."""
    client.post(
        "/api/jobs/",
        json={
            "title": "Rust Masterclass",
            "organization": "Rust Foundation",
            "date_of_issue": "2026-10-15",
            "recipients": [
                {"name": "Ferris Crab", "email": "ferris@rust-lang.org"},
                {"name": "John Crab", "email": "john@rust-lang.org"},
            ],
        },
    )
    res = client.get("/api/certificates/?search=Ferris")
    assert res.status_code == 200
    data = res.json()
    assert any(c["recipient_name"] == "Ferris Crab" for c in data["items"])


def test_preview_and_download_zip_and_delete_certificate(
    client: TestClient,
) -> None:
    """Test previewing PDF, downloading ZIP archive, and deleting certificate."""
    create_resp = client.post(
        "/api/jobs/",
        json={
            "title": "DevOps Immersion",
            "organization": "Linux Foundation",
            "date_of_issue": "2026-10-15",
            "recipients": [
                {"name": "Linus Torvalds", "email": "linus@kernel.org"},
                {"name": "Ken Thompson"},
            ],
        },
    )
    job_id = create_resp.json()["job_id"]

    # Test download ZIP
    zip_resp = client.get(f"/api/jobs/{job_id}/download-zip/")
    assert zip_resp.status_code == 200
    assert zip_resp.headers["content-type"] == "application/zip"
    assert "zip" in zip_resp.headers.get("content-disposition", "")
    assert zip_resp.content.startswith(b"PK")  # ZIP magic bytes

    # Test preview PDF
    certs = client.get(f"/api/jobs/{job_id}/certificates/").json()
    cert_id = certs[0]["id"]

    preview_resp = client.get(f"/api/certificates/{cert_id}/preview/")
    assert preview_resp.status_code == 200
    assert preview_resp.headers["content-type"] == "application/pdf"
    assert "inline" in preview_resp.headers.get("content-disposition", "")

    # Test delete certificate
    del_resp = client.delete(f"/api/certificates/{cert_id}/")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "success"

    # Confirm cert is gone
    check_resp = client.get(f"/api/certificates/{cert_id}/download/")
    assert check_resp.status_code == 404

    # Deleting again returns 404
    del_again = client.delete(f"/api/certificates/{cert_id}/")
    assert del_again.status_code == 404


def test_download_zip_nonexistent_and_empty_jobs(
    client: TestClient, db_session
) -> None:
    """Test download ZIP error scenarios."""
    # Unknown job -> 404
    r1 = client.get("/api/jobs/missing-job-id/download-zip/")
    assert r1.status_code == 404

    # Job with no certs -> 400
    from app.models import Job

    empty_job = Job(
        title="Empty Job",
        organization="Org",
        date_of_issue="2026-10-15",
        total_recipients=0,
    )
    db_session.add(empty_job)
    db_session.commit()

    r2 = client.get(f"/api/jobs/{empty_job.id}/download-zip/")
    assert r2.status_code == 400


def test_preview_certificate_error_cases(
    client: TestClient, db_session, temp_output_dir: Path
) -> None:
    """Test preview errors: 404, 400 failed, 403 traversal, and 404 missing."""
    from app.models import Certificate, Job

    job = Job(
        title="Preview Test",
        organization="Preview Org",
        date_of_issue="2026-10-15",
        total_recipients=3,
        failed_count=1,
    )
    db_session.add(job)
    db_session.flush()

    # 404 for unknown cert
    r_unknown = client.get("/api/certificates/non-existent-id/preview/")
    assert r_unknown.status_code == 404

    # 400 for failed cert
    failed_cert = Certificate(
        job_id=job.id,
        recipient_name="Failed Person",
        status="failed",
        error_message="Font rendering failed",
    )
    db_session.add(failed_cert)
    db_session.flush()

    r_failed = client.get(f"/api/certificates/{failed_cert.id}/preview/")
    assert r_failed.status_code == 400

    # 403 for path traversal
    evil_cert = Certificate(
        job_id=job.id,
        recipient_name="Hacker",
        status="success",
        file_path="/etc/passwd",
    )
    db_session.add(evil_cert)
    db_session.flush()

    r_evil = client.get(f"/api/certificates/{evil_cert.id}/preview/")
    assert r_evil.status_code == 403

    # 404 for missing physical file inside storage
    missing_file = temp_output_dir / "ghost.pdf"
    ghost_cert = Certificate(
        job_id=job.id,
        recipient_name="Ghost",
        status="success",
        file_path=str(missing_file),
    )
    db_session.add(ghost_cert)
    db_session.commit()

    r_ghost = client.get(f"/api/certificates/{ghost_cert.id}/preview/")
    assert r_ghost.status_code == 404


def test_dashboard_fallback_when_static_missing(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    """When index.html is missing, root returns API json welcome fallback."""
    monkeypatch.setattr("app.main.STATIC_DIR", tmp_path / "empty_dir")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "documentation" in resp.json()


def test_certificate_filtering_and_delete_failed(
    client: TestClient, db_session
) -> None:
    """Test filtering by job_id and status, and deleting a failed cert."""
    from app.models import Certificate, Job

    job = Job(
        title="Filter Test",
        organization="Filter Org",
        date_of_issue="2026-10-15",
        total_recipients=2,
        successful_count=1,
        failed_count=1,
    )
    db_session.add(job)
    db_session.flush()

    c_fail = Certificate(
        job_id=job.id,
        recipient_name="Failed User",
        status="failed",
        file_path="/outside/bad_file.pdf",
    )
    db_session.add(c_fail)
    db_session.commit()

    # Filter by job_id
    r_job = client.get(f"/api/certificates/?job_id={job.id}")
    assert r_job.status_code == 200
    assert r_job.json()["total"] >= 1

    # Filter by status
    r_status = client.get("/api/certificates/?status=failed")
    assert r_status.status_code == 200
    assert any(c["recipient_name"] == "Failed User" for c in r_status.json()["items"])

    # Delete failed cert with external path (tests safe error recovery)
    del_res = client.delete(f"/api/certificates/{c_fail.id}/")
    assert del_res.status_code == 200
    assert job.failed_count == 0


def test_parse_recipients_from_json(client: TestClient) -> None:
    """Verify parsing recipient lists from uploaded JSON file."""
    import json

    json_data = json.dumps(
        [
            {"name": "Alice Wonder", "email": "alice@wonder.com"},
            {"name": "Bob Builder", "email": "bob@builder.com"},
        ]
    ).encode("utf-8")

    response = client.post(
        "/api/recipients/parse-file/",
        files={"file": ("participants.json", json_data, "application/json")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 2
    assert data["recipients"][0]["name"] == "Alice Wonder"
    assert data["recipients"][1]["name"] == "Bob Builder"


def test_parse_recipients_from_csv(client: TestClient) -> None:
    """Verify parsing recipient lists from uploaded CSV file."""
    csv_data = "Name,Email\nJohn Doe,john@example.com\nJane Smith,\n".encode("utf-8")

    response = client.post(
        "/api/recipients/parse-file/",
        files={"file": ("users.csv", csv_data, "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 2
    assert data["recipients"][0]["name"] == "John Doe"
    assert data["recipients"][0]["email"] == "john@example.com"
    assert data["recipients"][1]["name"] == "Jane Smith"
    assert data["recipients"][1]["email"] is None


def test_parse_recipients_from_excel(client: TestClient) -> None:
    """Verify parsing recipient lists from uploaded Excel (.xlsx) file."""
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Full Name", "Email Address"])
    ws.append(["Emma Watson", "emma@actors.org"])
    ws.append(["Daniel Radcliffe", "daniel@actors.org"])

    buf = io.BytesIO()
    wb.save(buf)
    excel_data = buf.getvalue()

    response = client.post(
        "/api/recipients/parse-file/",
        files={
            "file": (
                "cast.xlsx",
                excel_data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 2
    assert data["recipients"][0]["name"] == "Emma Watson"
    assert data["recipients"][1]["name"] == "Daniel Radcliffe"


def test_parse_recipients_invalid_or_empty_file(client: TestClient) -> None:
    """Verify error handling for invalid or empty files."""
    # Empty file
    resp_empty = client.post(
        "/api/recipients/parse-file/",
        files={"file": ("empty.json", b"", "application/json")},
    )
    assert resp_empty.status_code == 400

    # Unsupported format
    resp_unsupported = client.post(
        "/api/recipients/parse-file/",
        files={"file": ("data.pdf", b"%PDF-1.4...", "application/pdf")},
    )
    assert resp_unsupported.status_code == 400

    # Malformed JSON
    resp_bad_json = client.post(
        "/api/recipients/parse-file/",
        files={"file": ("bad.json", b"{invalid json", "application/json")},
    )
    assert resp_bad_json.status_code == 400


def test_create_job_with_signature_and_process(
    client: TestClient, db_session, monkeypatch
) -> None:
    """Verify job creation with signature image and generation pipeline."""
    from unittest.mock import MagicMock

    from app.services.job_service import JobService

    mock_delay = MagicMock()
    mock_delay.return_value.id = "mock-celery-task-id"
    monkeypatch.setattr("app.tasks.process_job_task.delay", mock_delay)

    tiny_png_b64 = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJA"
        "AAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )

    resp = client.post(
        "/api/jobs/",
        json={
            "title": "Signature Masterclass",
            "organization": "Auth Dept",
            "date_of_issue": "2026-10-15",
            "signature_data": tiny_png_b64,
            "recipients": [{"name": "Signed Recipient", "email": "sig@example.com"}],
        },
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Process job directly and verify signature image rendered without error
    service = JobService(db=db_session)
    job = service.process_job(job_id)
    assert job.status == "completed"
    assert job.successful_count == 1
    assert job.signature_data == tiny_png_b64


def test_websocket_endpoint_connect_and_broadcast(client: TestClient) -> None:
    """Verify WebSocket endpoint connection and manager broadcasting."""
    import asyncio

    from app.websockets import manager as ws_manager

    with client.websocket_connect("/ws/jobs") as ws:
        # Broadcast an event through ws_manager
        asyncio.run(
            ws_manager.broadcast(
                {
                    "event": "job_progress",
                    "job_id": "test-ws-id",
                    "processed": 5,
                    "total": 10,
                    "percent": 50,
                }
            )
        )
        msg = ws.receive_json()
        assert msg["event"] == "job_progress"
        assert msg["job_id"] == "test-ws-id"
        assert msg["percent"] == 50


def test_download_selected_certificates_zip(
    client: TestClient, db_session, monkeypatch
) -> None:
    """Verify group downloading of selected certificates as a single ZIP."""
    import io
    import zipfile
    from unittest.mock import MagicMock

    from app.services.job_service import JobService

    mock_delay = MagicMock()
    mock_delay.return_value.id = "mock-zip-task-id"
    monkeypatch.setattr("app.tasks.process_job_task.delay", mock_delay)

    resp = client.post(
        "/api/jobs/",
        json={
            "title": "Selected ZIP Test",
            "organization": "Batch Dept",
            "date_of_issue": "2026-10-15",
            "recipients": [
                {"name": "Alice Winner", "email": "alice@example.com"},
                {"name": "Bob Champion", "email": "bob@example.com"},
            ],
        },
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    service = JobService(db=db_session)
    service.process_job(job_id)

    certs = service.get_certificates(job_id)
    cert_ids = [c.id for c in certs]
    assert len(cert_ids) == 2

    # Request ZIP of selected certificates
    zip_resp = client.post(
        "/api/certificates/download-selected-zip/",
        json={"certificate_ids": cert_ids},
    )
    assert zip_resp.status_code == 200
    assert zip_resp.headers["content-type"] == "application/zip"

    # Verify zip content
    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
        namelist = zf.namelist()
        assert len(namelist) == 2
        assert any("Alice_Winner" in n for n in namelist)
        assert any("Bob_Champion" in n for n in namelist)

    # Empty / nonexistent IDs return 400
    bad_resp = client.post(
        "/api/certificates/download-selected-zip/",
        json={"certificate_ids": ["nonexistent-id-1", "nonexistent-id-2"]},
    )
    assert bad_resp.status_code == 400


def test_s3_presigned_url_rewrite_docker_host() -> None:
    """Verify S3StorageBackend rewrites docker-internal hostnames for browser access."""
    from unittest.mock import MagicMock

    from app.config import Settings
    from app.storage.s3 import S3StorageBackend

    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = (
        "http://rustfs:9000/certificates/job1/cert1.pdf?AWSAccessKeyId=test"
    )

    settings = Settings(
        s3_endpoint_url="http://rustfs:9000",
        s3_access_key_id="test",
        s3_secret_access_key="test",
        s3_bucket_name="certificates",
    )
    backend = S3StorageBackend(settings=settings)
    backend.client = mock_client

    url = backend.get_presigned_url("job1/cert1.pdf")
    assert url is not None
    assert "http://localhost:9000" in url
    assert "rustfs:9000" not in url
