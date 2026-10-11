import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import init_db
from app.routers.jobs import router as jobs_router
from app.websockets import manager as ws_manager
from app.websockets import start_redis_listener

settings = get_settings()

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager to handle startup and shutdown logic."""
    # Ensure database schema is created
    init_db()

    # Ensure output storage directory exists
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)

    # Start background Redis PubSub listener for WebSockets
    redis_task = asyncio.create_task(
        start_redis_listener(ws_manager, settings.redis_url)
    )

    try:
        yield
    finally:
        redis_task.cancel()


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=(
        "Production-ready backend API for bulk certificate generation and file "
        "management using Celery, Redis, ReportLab, and SQLite/PostgreSQL."
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

# Mount static assets for frontend dashboard & file manager
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount API routers
app.include_router(jobs_router)


@app.websocket("/ws/jobs")
async def websocket_jobs(websocket: WebSocket) -> None:
    """Live WebSocket endpoint for streaming job progress and certificate updates."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection open / listen for heartbeat ping
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


@app.get("/", tags=["UI Dashboard"], summary="Certificate File Manager Dashboard")
@app.get(
    "/manager", tags=["UI Dashboard"], summary="Certificate File Manager Dashboard"
)
def serve_dashboard():
    """Serve the Certificate File Manager web user interface."""
    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file), media_type="text/html")
    return {
        "message": "Welcome to Bulk Certificate Generator API",
        "documentation": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    """Health check endpoint to verify API server availability."""
    return {
        "status": "healthy",
        "service": settings.app_title,
        "version": settings.app_version,
    }


@app.get("/api/info", tags=["System"])
def api_info() -> dict[str, str]:
    """System information endpoint."""
    return {
        "message": "Bulk Certificate Generator API",
        "documentation": "/docs",
        "health": "/health",
        "dashboard": "/",
    }
