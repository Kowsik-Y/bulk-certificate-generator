"""Unit tests for ReportLab PDF certificate generation."""

from pathlib import Path

import pytest

from app.generator.certificate_generator import generate_certificate


def test_generate_certificate_creates_valid_pdf(tmp_path: Path) -> None:
    """Certificate generator creates a non-empty PDF file starting with %PDF."""
    output_file = tmp_path / "cert_1.pdf"
    result = generate_certificate(
        recipient_name="Grace Hopper",
        title="Advanced Systems Programming",
        organization="Computer History Society",
        date_of_issue="2026-10-15",
        output_path=str(output_file),
    )

    assert result == str(output_file)
    assert output_file.is_file()
    assert output_file.stat().st_size > 1000

    content = output_file.read_bytes()
    assert content.startswith(b"%PDF")


def test_generate_with_special_characters(tmp_path: Path) -> None:
    """Names with accents and hyphens generate without errors."""
    output_file = tmp_path / "cert_special.pdf"
    result = generate_certificate(
        recipient_name="Jean-Luc Picard & René Descartes",
        title="Starfleet Command & Philosophy 101",
        organization="United Federation of Planets",
        date_of_issue="2026-10-15",
        output_path=str(output_file),
    )

    assert Path(result).is_file()
    assert Path(result).stat().st_size > 1000


def test_generate_with_empty_name_raises_error(tmp_path: Path) -> None:
    """Empty or whitespace recipient name raises ValueError."""
    output_file = tmp_path / "cert_err.pdf"
    with pytest.raises(ValueError, match="Recipient name"):
        generate_certificate(
            recipient_name="   ",
            title="Python Course",
            organization="Org",
            date_of_issue="2026-10-15",
            output_path=str(output_file),
        )


def test_generate_with_empty_title_raises_error(tmp_path: Path) -> None:
    """Empty course title raises ValueError."""
    output_file = tmp_path / "cert_err.pdf"
    with pytest.raises(ValueError, match="Title"):
        generate_certificate(
            recipient_name="John Doe",
            title="",
            organization="Org",
            date_of_issue="2026-10-15",
            output_path=str(output_file),
        )


def test_generate_with_empty_organization_raises_error(tmp_path: Path) -> None:
    """Empty organization raises ValueError."""
    output_file = tmp_path / "cert_err.pdf"
    with pytest.raises(ValueError, match="Organization"):
        generate_certificate(
            recipient_name="John Doe",
            title="Python Course",
            organization="   ",
            date_of_issue="2026-10-15",
            output_path=str(output_file),
        )


def test_generate_with_empty_date_raises_error(tmp_path: Path) -> None:
    """Empty date of issue raises ValueError."""
    output_file = tmp_path / "cert_err.pdf"
    with pytest.raises(ValueError, match="Date of issue"):
        generate_certificate(
            recipient_name="John Doe",
            title="Python Course",
            organization="Org",
            date_of_issue="",
            output_path=str(output_file),
        )
