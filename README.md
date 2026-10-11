# Bulk Certificate Generator

A high-performance, asynchronous backend API built with **FastAPI**, **Celery**, **Redis**, and **ReportLab** for generating PDF certificates in bulk.

---

## Features

- ⚡ **Asynchronous Job Processing**: Submit bulk certificate requests and receive immediate acknowledgement (`202 Accepted`). Certificate generation executes in background workers powered by Celery and Redis.
- 🛡️ **Per-Certificate Error Isolation**: A rendering error or malformed data in an individual certificate does **not** fail the batch. Successful certificates are persisted and made downloadable, while failures are captured with descriptive error messages.
- 🎨 **Vector PDF Generation**: Uses ReportLab canvas drawing to generate crisp, print-ready landscape certificates (ivory background, double gold borders, corner ornaments, official seals, and custom typography) with zero external image dependencies.
- 📐 **Strict Data Validation**: Validates all payload structures at the API boundary using Pydantic v2 (name formatting, non-blank checks, regex for emails and ISO dates).
- 🔄 **Fault-Tolerant & Durable**: Celery tasks feature `acks_late=True`, exponential backoff retry policies, and `worker_prefetch_multiplier=1` for fair queue balancing.
- 📦 **Layered Architecture**: Clean separation between Routers, Service Layer, Repository Layer, and PDF Generator.
- 🧪 **100% Test Coverage**: Comprehensive test suite covering API contracts, validation edge cases, ReportLab PDF rendering, service layer logic, and failure resilience.

---

## Architecture

```mermaid
graph TD
    Client[Client / Frontend] -->|POST /api/jobs/| Router[FastAPI Router]
    Client -->|GET /api/jobs/{id}/| Router
    Client -->|GET /api/jobs/{id}/certificates/| Router
    Client -->|GET /api/certificates/{id}/download/| Router

    Router --> Service[JobService]
    Service --> Repo[JobRepository]
    Repo --> DB[(SQLite / PostgreSQL)]

    Service -->|Dispatch Task| Redis[(Redis Broker)]
    Redis --> Worker[Celery Worker]
    Worker --> Generator[ReportLab Generator]
    Generator --> Filesystem[(PDF Output Storage)]
    Worker --> Repo
```

### Processing Lifecycle

1. **Submit Job**: `POST /api/jobs/` accepts recipient data and event metadata.
2. **Persistence**: Job record and individual recipient certificate records are created in `pending` status.
3. **Dispatch**: A Celery task is enqueued to Redis and returns immediately with `job_id`.
4. **Worker Execution**: Celery worker picks up the job, switches status to `processing`, and generates each certificate in an isolated `try/except` boundary.
5. **Terminal State**: When all recipients are processed, job status transitions to `completed` (or `completed_with_errors` if partial failures occurred).
6. **Download**: Generated PDFs can be individually downloaded via `GET /api/certificates/{id}/download/`.

---

## Tech Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Web Framework** | FastAPI | High-performance asynchronous API, auto OpenAPI documentation, dependency injection |
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

### 1. Clone & Set Up Virtual Environment

```bash
cd "Bulk Certificate Generator"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Start Redis Broker

```bash
docker compose up -d
```

*(Or verify local Redis is running on `redis://localhost:6379/0`)*

### 3. Run Celery Worker

In a dedicated terminal window:

```bash
source venv/bin/activate
celery -A app.celery_app:celery_app worker --loglevel=info
```

### 4. Run API Server

In another terminal window:

```bash
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Interactive API documentation will be available at:
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

## Testing & Quality

Tests run in-memory with Celery in **eager mode** (`task_always_eager=True`), meaning no running Redis or Celery worker process is needed to execute the test suite!

```bash
# Run pytest
pytest -v

# Run with test coverage
pytest --cov=app --cov-report=term-missing

# Lint & Format checks
ruff check app tests
ruff format --check app tests
```

---

## Project Structure

```
Bulk Certificate Generator/
├── app/
│   ├── __init__.py
│   ├── config.py                  # Pydantic Settings
│   ├── database.py                # SQLAlchemy Engine, Session, Base
│   ├── models.py                  # Job & Certificate ORM models
│   ├── schemas.py                 # Pydantic request/response models
│   ├── celery_app.py              # Celery app instance & settings
│   ├── tasks.py                   # Celery background tasks with retry
│   ├── generator/
│   │   ├── __init__.py
│   │   └── certificate_generator.py # ReportLab PDF canvas drawing
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── job_repository.py      # Database CRUD operations
│   ├── services/
│   │   ├── __init__.py
│   │   └── job_service.py         # Business logic & error isolation
│   ├── routers/
│   │   ├── __init__.py
│   │   └── jobs.py                # FastAPI HTTP routes
│   └── main.py                    # FastAPI application & lifespan
├── output/                        # Default storage directory for PDFs
├── tests/
│   ├── conftest.py                # Test fixtures (SQLite in-memory, eager Celery)
│   ├── test_api.py                # HTTP integration tests
│   ├── test_validation.py         # Pydantic payload validation tests
│   ├── test_generator.py          # ReportLab PDF unit tests
│   ├── test_service.py            # JobService business logic tests
│   ├── test_tasks.py              # Celery task retry tests
│   └── test_failure_handling.py   # Partial failure resilience tests
├── docker-compose.yml             # Redis container configuration
├── pyproject.toml                 # Tool configuration (Ruff, Pytest, Coverage)
├── requirements.txt               # Dependencies
└── README.md
```
