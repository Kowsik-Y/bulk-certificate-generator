# Bulk Certificate Generator

A high-performance, asynchronous backend API built with **FastAPI**, **Celery**, **Redis**, and **ReportLab** for generating PDF certificates in bulk.

---

## Features

- **Asynchronous Job Processing**: Submit bulk certificate requests and receive immediate acknowledgement (`202 Accepted`). Certificate generation executes in background workers powered by Celery and Redis.
- **Per-Certificate Error Isolation**: A rendering error or malformed data in an individual certificate does **not** fail the batch. Successful certificates are persisted and made downloadable, while failures are captured with descriptive error messages.
- **Pluggable Storage Backends (RustFS / MinIO / Local)**: Store generated PDF certificates in S3-compatible high-performance object storage like **RustFS** or **MinIO** with automatic bucket creation, presigned URLs, and streaming downloads, or on local volumes.
- **Vector PDF Generation**: Uses ReportLab canvas drawing to generate crisp, print-ready landscape certificates (ivory background, double gold borders, corner ornaments, official seals, and custom typography) with zero external image dependencies.
- **Strict Data Validation**: Validates all payload structures at the API boundary using Pydantic v2 (name formatting, non-blank checks, regex for emails and ISO dates).
- **Fault-Tolerant & Durable**: Celery tasks feature `acks_late=True`, exponential backoff retry policies, and `worker_prefetch_multiplier=1` for fair queue balancing.
- **Layered Architecture**: Clean separation between Routers, Service Layer, Storage Layer, Repository Layer, and PDF Generator.
- **100% Test Coverage**: Comprehensive test suite covering API contracts, validation edge cases, ReportLab PDF rendering, service layer logic, S3/RustFS storage, and failure resilience.

---

## Architecture

```mermaid
graph TD
    Client[Client / Frontend Dashboard] -->|POST /api/jobs/| Router[FastAPI Router]
    Client -->|GET /api/certificates/{id}/download/| Router
    Client -->|GET /api/jobs/{id}/download-zip/| Router

    Router --> Service[JobService]
    Service --> Repo[JobRepository]
    Repo --> DB[(SQLite / PostgreSQL)]

    Service -->|Dispatch Task| Redis[(Redis Broker)]
    Redis --> Worker[Celery Worker]
    Worker --> Generator[ReportLab Generator]
    Worker --> Storage[Storage Backend]
    Storage -->|S3 API| RustFS[(RustFS / MinIO S3 Bucket)]
    Storage -->|Local| Filesystem[(Local Volume Storage)]
    Worker --> Repo
```

### Processing Lifecycle

1. **Submit Job**: `POST /api/jobs/` accepts recipient data and event metadata.
2. **Persistence**: Job record and individual recipient certificate records are created in `pending` status.
3. **Dispatch**: A Celery task is enqueued to Redis and returns immediately with `job_id`.
4. **Worker Execution**: Celery worker picks up the job, switches status to `processing`, and generates each certificate in an isolated `try/except` boundary.
5. **Storage**: In S3 mode, generated PDF bytes stream directly into the configured RustFS / MinIO bucket (`s3://certificates/{job_id}/{cert_id}.pdf`). In local mode, they are saved to the output volume.
6. **Terminal State**: When all recipients are processed, job status transitions to `completed` (or `completed_with_errors` if partial failures occurred).
7. **Download & Management**: Generated PDFs can be downloaded, previewed inline, or exported as a ZIP archive through the API or the built-in web File Manager.

---

## Tech Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Web Framework** | FastAPI | High-performance asynchronous API, auto OpenAPI documentation, dependency injection |
| **Object Storage** | RustFS / MinIO / S3 | High-performance, S3-compatible distributed storage with web management console |
| **Data Validation** | Pydantic v2 | Strict schema enforcement, custom validators, fast Rust core |
| **Task Queue** | Celery + Redis | Durable background processing, tasks survive restarts, retry policies, monitoring |
| **Database** | SQLAlchemy 2.0 (SQLite / PostgreSQL) | Clean ORM with repository pattern, zero-config SQLite default |
| **PDF Rendering** | ReportLab | Native vector canvas drawing, self-contained, high visual quality |
| **Code Quality** | Ruff & Pytest | Strict formatting, linting, and 100% test coverage |

---

## Quickstart

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for Redis) or local Redis server

### Option A: Run via Docker (Recommended — Single Command)

Builds the application image and starts Redis, RustFS S3 Object Storage, FastAPI, and Celery Worker containers simultaneously:

**Linux / macOS:**
```bash
./docker-run.sh
# Or: docker compose up --build
```

**Windows (PowerShell):**
```powershell
.\docker-run.ps1
# Or: docker compose up --build
```

---

### Option B: Interactive Initialization Scripts

Use the automated initialization script to set up Python virtualenv, install dependencies, run Redis, and launch services:

**Linux / macOS:**
```bash
./init.sh          # Interactive Menu
./init.sh --docker # Directly launch Docker container stack
./init.sh --local  # Set up venv and run locally on host
./init.sh --test   # Run test suite with coverage
```

**Windows (PowerShell):**
```powershell
.\init.ps1               # Interactive Menu
.\init.ps1 -Mode Docker  # Directly launch Docker container stack
.\init.ps1 -Mode Local   # Set up venv and run locally on host
.\init.ps1 -Mode Test    # Run test suite with coverage
```

---

### Option C: Manual Local Setup (Step-by-Step)

```bash
# 1. Create & activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start Redis broker
docker compose up -d redis

# 4. Terminal 1: Start Celery worker
celery -A app.celery_app:celery_app worker --loglevel=info

# 5. Terminal 2: Start FastAPI web server
uvicorn app.main:app --reload --port 8000
```

Interactive API documentation:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)


---

## API Reference

### 1. Create Certificate Generation Job

`POST /api/jobs/` — **Status: 202 Accepted**

```bash
curl -X POST http://localhost:8000/api/jobs/ \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Full Stack Python Mastery",
    "organization": "Engineering Institute",
    "date_of_issue": "2026-10-15",
    "recipients": [
      {"name": "Alice Johnson", "email": "alice@example.com"},
      {"name": "Bob Smith", "email": "bob@example.com"},
      {"name": "Charlie Day"}
    ]
  }'
```

**Response:**
```json
{
  "job_id": "7a353d26-7249-4115-bb8a-211aa53d2f34",
  "status": "pending",
  "message": "Job created. 3 certificates queued for generation."
}
```

---

### 2. Poll Job Progress & Status

`GET /api/jobs/{job_id}/` — **Status: 200 OK**

```bash
curl http://localhost:8000/api/jobs/7a353d26-7249-4115-bb8a-211aa53d2f34/
```

**Response:**
```json
{
  "id": "7a353d26-7249-4115-bb8a-211aa53d2f34",
  "status": "completed",
  "title": "Full Stack Python Mastery",
  "organization": "Engineering Institute",
  "date_of_issue": "2026-10-15",
  "total_recipients": 3,
  "successful_count": 3,
  "failed_count": 0,
  "created_at": "2026-10-15T12:00:00",
  "completed_at": "2026-10-15T12:00:02"
}
```

---

### 3. List All Certificates for a Job

`GET /api/jobs/{job_id}/certificates/` — **Status: 200 OK**

```bash
curl http://localhost:8000/api/jobs/7a353d26-7249-4115-bb8a-211aa53d2f34/certificates/
```

**Response:**
```json
[
  {
    "id": "99dca212-04fd-4bc3-a9d9-bb47ad3f9829",
    "recipient_name": "Alice Johnson",
    "recipient_email": "alice@example.com",
    "status": "success",
    "error_message": null,
    "file_path": "./output/99dca212-04fd-4bc3-a9d9-bb47ad3f9829.pdf"
  },
  {
    "id": "e444453b-e1bc-40d6-be81-9b7e411adca1",
    "recipient_name": "Bob Smith",
    "recipient_email": "bob@example.com",
    "status": "success",
    "error_message": null,
    "file_path": "./output/e444453b-e1bc-40d6-be81-9b7e411adca1.pdf"
  }
]
```

---

### 4. Download Certificate PDF

`GET /api/certificates/{certificate_id}/download/` — **Status: 200 OK**

```bash
curl -OJ http://localhost:8000/api/certificates/99dca212-04fd-4bc3-a9d9-bb47ad3f9829/download/
```

Downloads `certificate_Alice_Johnson.pdf` directly.

---

### 5. Preview Certificate Inline

`GET /api/certificates/{certificate_id}/preview/` — **Status: 200 OK**

Streams the PDF inline (`Content-Disposition: inline`) for browser embedding or modal viewer.

---

### 6. Batch Download Job as ZIP

`GET /api/jobs/{job_id}/download-zip/` — **Status: 200 OK**

```bash
curl -OJ http://localhost:8000/api/jobs/{job_id}/download-zip/
```

Packages all successfully generated certificates in the job into a sanitized ZIP archive (`certificates_job_{job_id}.zip`).

---

### 7. File Manager Search & Filter Query

`GET /api/certificates/?search=Alice&status=success&skip=0&limit=50` — **Status: 200 OK**

Returns paginated certificates with file sizes, creation timestamps, and download links.

---

### 8. Delete Certificate

`DELETE /api/certificates/{certificate_id}/` — **Status: 200 OK**

Safely removes the certificate from the database and physically deletes the PDF file from disk, while adjusting parent job metrics.

---

### 9. System Storage & Metrics

`GET /api/stats/` — **Status: 200 OK**

Returns aggregated storage metrics (`total_jobs`, `total_certificates`, `successful_certificates`, `failed_certificates`, `total_storage_bytes`, `total_storage_formatted`).

---

## Certificate File Manager Web Dashboard

An interactive dashboard is served directly at:
- **`http://localhost:8000/`** or **`http://localhost:8000/manager`**

### Features:
- **Real-time Storage Overview**: Live disk usage, total jobs, and success/failure tallies.
- **Live Search & Filter**: Filter by recipient name, email, or status (`all`, `success`, `pending`, `failed`).
- **In-Browser PDF Modal Preview**: Instant visual preview modal without leaving the dashboard.
- **One-Click Batch ZIP Download**: Export entire batches with clean file naming.
- **Safe File Deletion**: Delete individual certificates with physical storage cleanup.
- **Built-in Batch Dispatcher**: Launch new certificate generation batches directly from a modern modal dialog.
- **Rich Dark Aesthetics**: Glassmorphism UI built with Vanilla CSS and Vanilla JS (zero frontend build step needed).

---

## Testing & Quality

Tests run in-memory with Celery in **eager mode** (`task_always_eager=True`), meaning no running Redis or Celery worker process is needed to execute the test suite!

```bash
# Run pytest with test coverage
pytest --cov=app --cov-report=term-missing

# Lint & Format checks
ruff check app tests
ruff format --check app tests

# Static type safety inspection
mypy app
```

---

## Configuration & Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./certificates.db` | SQLAlchemy database connection string (SQLite / PostgreSQL) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis broker and backend URL for Celery |
| `STORAGE_BACKEND` | `local` | Storage mode: `local` (volume) or `rustfs` / `s3` / `minio` |
| `S3_ENDPOINT_URL` | `None` (`http://rustfs:9000` in Docker) | S3-compatible service URL (RustFS, MinIO, or LocalStack) |
| `S3_ACCESS_KEY_ID` | `rustfsadmin` | S3 Access Key ID |
| `S3_SECRET_ACCESS_KEY` | `rustfsadmin` | S3 Secret Access Key |
| `S3_BUCKET_NAME` | `certificates` | Target bucket for certificate objects (auto-created if missing) |
| `OUTPUT_DIR` | `./output` | Host storage directory for local mode and temporary ZIP staging |
| `MAX_RECIPIENTS_PER_BATCH` | `1000` | Maximum recipients allowed in a single request |

---

## RustFS S3 Web Management Console

When running with Docker Compose:
- **RustFS S3 API**: `http://localhost:9000`
- **RustFS Web Management Console**: `http://localhost:9001`
- **Default Credentials**: `rustfsadmin` / `rustfsadmin`

You can log into the console at `http://localhost:9001` to view your `certificates` bucket, inspect object trees, track storage usage, or download files directly from the browser!

---

## Project Structure

```
Bulk Certificate Generator/
├── app/
│   ├── __init__.py
│   ├── config.py                  # Pydantic Settings & Storage configuration
│   ├── database.py                # SQLAlchemy Engine, Session, Base
│   ├── models.py                  # Job & Certificate ORM models
│   ├── schemas.py                 # Pydantic request/response models
│   ├── celery_app.py              # Celery app instance & settings
│   ├── tasks.py                   # Celery background tasks with retry
│   ├── generator/
│   │   ├── __init__.py
│   │   └── certificate_generator.py # ReportLab PDF canvas drawing & in-memory bytes
│   ├── storage/
│   │   ├── __init__.py            # Storage factory & singleton getters
│   │   ├── base.py                # StorageBackend abstract interface & errors
│   │   ├── local.py               # Local filesystem storage backend
│   │   └── s3.py                  # S3 storage backend (RustFS / MinIO / AWS S3)
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── job_repository.py      # Database CRUD operations
│   ├── services/
│   │   ├── __init__.py
│   │   └── job_service.py         # Business logic & error isolation
│   ├── routers/
│   │   ├── __init__.py
│   │   └── jobs.py                # FastAPI HTTP routes
│   ├── static/                    # Certificate File Manager web assets
│   │   ├── css/styles.css         # Glassmorphism dark-mode stylesheet
│   │   ├── js/app.js              # Vanilla JS frontend application
│   │   └── index.html             # Certificate File Manager dashboard
│   └── main.py                    # FastAPI application & lifespan
├── output/                        # Default storage directory for PDFs
├── tests/
│   ├── conftest.py                # Test fixtures (SQLite in-memory, eager Celery)
│   ├── test_api.py                # HTTP integration tests
│   ├── test_validation.py         # Pydantic payload validation tests
│   ├── test_generator.py          # ReportLab PDF unit tests
│   ├── test_service.py            # JobService business logic tests
│   ├── test_storage.py            # Storage backend tests (Local and S3/RustFS)
│   ├── test_tasks.py              # Celery task retry tests
│   └── test_failure_handling.py   # Partial failure resilience tests
├── .dockerignore                  # Docker build context exclusions
├── docker-compose.yml             # Full stack container configuration (Redis, RustFS, API, Worker)
├── Dockerfile                     # Multi-stage container build image
├── init.sh                        # POSIX Bash initialization & runner script
├── init.ps1                       # Windows PowerShell initialization & runner script
├── docker-run.sh                  # One-command Docker stack launcher (Linux/macOS)
├── docker-run.ps1                 # One-command Docker stack launcher (Windows)
├── pyproject.toml                 # Tool configuration (Ruff, Pytest, Coverage, Mypy)
├── requirements.txt               # Dependencies
└── README.md
```



