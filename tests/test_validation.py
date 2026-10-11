"""Tests for input validation at API boundary."""

from fastapi.testclient import TestClient


def test_empty_recipients_list_rejected(client: TestClient) -> None:
    """Empty recipients list should fail validation with 422."""
    payload = {
        "title": "Data Science 101",
        "organization": "Data Org",
        "date_of_issue": "2026-10-15",
        "recipients": [],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 422


def test_missing_title_rejected(client: TestClient) -> None:
    """Missing title field returns 422."""
    payload = {
        "organization": "Data Org",
        "date_of_issue": "2026-10-15",
        "recipients": [{"name": "Alice"}],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 422


def test_missing_organization_rejected(client: TestClient) -> None:
    """Missing organization field returns 422."""
    payload = {
        "title": "Data Science 101",
        "date_of_issue": "2026-10-15",
        "recipients": [{"name": "Alice"}],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 422


def test_blank_title_rejected(client: TestClient) -> None:
    """Whitespace-only title returns 422."""
    payload = {
        "title": "   ",
        "organization": "Data Org",
        "date_of_issue": "2026-10-15",
        "recipients": [{"name": "Alice"}],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 422


def test_blank_organization_rejected(client: TestClient) -> None:
    """Whitespace-only organization returns 422."""
    payload = {
        "title": "Python Bootcamp",
        "organization": "   ",
        "date_of_issue": "2026-10-15",
        "recipients": [{"name": "Alice"}],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 422


def test_blank_recipient_name_rejected(client: TestClient) -> None:
    """Whitespace-only recipient name returns 422."""
    payload = {
        "title": "Python Bootcamp",
        "organization": "Tech Org",
        "date_of_issue": "2026-10-15",
        "recipients": [{"name": "   "}],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 422


def test_name_exceeding_max_length_rejected(client: TestClient) -> None:
    """Recipient name exceeding 200 characters returns 422."""
    payload = {
        "title": "Python Bootcamp",
        "organization": "Tech Org",
        "date_of_issue": "2026-10-15",
        "recipients": [{"name": "A" * 201}],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 422


def test_invalid_email_format_rejected(client: TestClient) -> None:
    """Malformed email strings return 422."""
    payload = {
        "title": "Python Bootcamp",
        "organization": "Tech Org",
        "date_of_issue": "2026-10-15",
        "recipients": [{"name": "Alice", "email": "invalid-email-address"}],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 422


def test_valid_email_accepted(client: TestClient) -> None:
    """Proper email format passes validation."""
    payload = {
        "title": "Python Bootcamp",
        "organization": "Tech Org",
        "date_of_issue": "2026-10-15",
        "recipients": [{"name": "Alice", "email": "alice.smith+tag@example.co.uk"}],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 202


def test_invalid_date_format_rejected(client: TestClient) -> None:
    """Non-conforming date string (e.g. DD/MM/YYYY) returns 422."""
    payload = {
        "title": "Python Bootcamp",
        "organization": "Tech Org",
        "date_of_issue": "15/10/2026",
        "recipients": [{"name": "Alice"}],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 422


def test_invalid_calendar_date_rejected(client: TestClient) -> None:
    """Non-existent calendar date returns 422."""
    payload = {
        "title": "Python Bootcamp",
        "organization": "Tech Org",
        "date_of_issue": "2026-02-31",
        "recipients": [{"name": "Alice"}],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 422


def test_whitespace_email_treated_as_none(client: TestClient) -> None:
    """Whitespace-only email is normalized to None and accepted."""
    payload = {
        "title": "Python Bootcamp",
        "organization": "Tech Org",
        "date_of_issue": "2026-10-15",
        "recipients": [{"name": "Alice", "email": "   "}],
    }
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 202
