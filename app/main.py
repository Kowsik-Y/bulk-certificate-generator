"""FastAPI application initialization and lifespan management."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers.jobs import router as jobs_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager to handle startup and shutdown logic."""
    # Ensure database schema is created
    init_db()

    # Ensure output storage directory exists
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)

    yield


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=(
        "Production-ready backend API for bulk certificate generation "
        "using Celery, Redis, ReportLab, and SQLite/PostgreSQL."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for cross-origin frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(jobs_router)


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    """Health check endpoint to verify API server availability."""
    return {
        "status": "healthy",
        "service": settings.app_title,
        "version": settings.app_version,
    }


@app.get("/", tags=["System"])
def root() -> dict[str, str]:
    """Root endpoint providing links to API documentation."""
    return {
        "message": "Welcome to Bulk Certificate Generator API",
        "documentation": "/docs",
        "health": "/health",
    }
