"""Pydantic schemas for request validation and response serialization."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[\w\-]+\.[\w\.\-]+$")
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class RecipientRequest(BaseModel):
    """Validation schema for an individual certificate recipient."""

    name: str = Field(
        ..., min_length=1, max_length=200, description="Recipient full name"
    )
    email: str | None = Field(
        None, max_length=320, description="Recipient email address"
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Name cannot be blank or whitespace only")
        if any(c in stripped for c in "\r\n\0"):
            raise ValueError("Name cannot contain newline or control characters")
        return stripped

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                return None
            if not EMAIL_REGEX.match(stripped):
                raise ValueError("Invalid email format")
            return stripped
        return v


class JobCreateRequest(BaseModel):
    """Validation schema for creating a bulk certificate generation job."""

    title: str = Field(
        ..., min_length=1, max_length=300, description="Event or course title"
    )
    organization: str = Field(
        ..., min_length=1, max_length=300, description="Issuing organization"
    )
    date_of_issue: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Date in YYYY-MM-DD format",
    )
    recipients: list[RecipientRequest] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of recipients (1 to 1000 recipients per batch)",
    )

    @field_validator("title")
    @classmethod
    def validate_title_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Title cannot be blank or whitespace only")
        if any(c in stripped for c in "\r\n\0"):
            raise ValueError("Title cannot contain newline or control characters")
        return stripped

    @field_validator("organization")
    @classmethod
    def validate_organization_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Organization cannot be blank or whitespace only")
        if any(c in stripped for c in "\r\n\0"):
            raise ValueError(
                "Organization cannot contain newline or control characters"
            )
        return stripped

    @field_validator("date_of_issue")
    @classmethod
    def validate_date_value(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as err:
            raise ValueError(
                "Date of issue must be a valid calendar date in YYYY-MM-DD format"
            ) from err
        return v


class CertificateResponse(BaseModel):
    """Schema for individual certificate information."""

    id: str
    recipient_name: str
    recipient_email: str | None = None
    status: str
    error_message: str | None = None
    file_path: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class JobStatusResponse(BaseModel):
    """Schema for job status and progress tracking."""

    id: str
    status: str
    title: str
    organization: str
    date_of_issue: str
    total_recipients: int
    successful_count: int
    failed_count: int
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class JobCreateResponse(BaseModel):
    """Schema returned immediately upon submitting a generation job."""

    job_id: str
    status: str
    message: str


class CertificateFileItemResponse(BaseModel):
    """Schema for certificate files displayed in the file manager."""

    id: str
    job_id: str
    job_title: str
    job_organization: str
    recipient_name: str
    recipient_email: str | None = None
    status: str
    file_size_bytes: int | None = None
    file_size_formatted: str | None = None
    error_message: str | None = None
    file_exists: bool = False
    created_at: datetime
    download_url: str
    preview_url: str
    presigned_url: str | None = None
    storage_backend: str = "local"


class CertificateListResponse(BaseModel):
    """Paginated list of certificate files."""

    total: int
    skip: int
    limit: int
    items: list[CertificateFileItemResponse]


class SystemStatsResponse(BaseModel):
    """System-wide file storage and job metrics."""

    total_jobs: int
    total_certificates: int
    successful_certificates: int
    failed_certificates: int
    total_storage_bytes: int
    total_storage_formatted: str
    storage_backend: str = "local"
    bucket_name: str | None = None


class ParseRecipientsResponse(BaseModel):
    """Schema for parsed recipient list uploaded from file."""

    recipients: list[RecipientRequest]
    total_count: int
    filename: str
