#!/usr/bin/env bash
# ==============================================================================
# Bulk Certificate Generator — Project Initialization & Runner Script
# Usage:
#   ./init.sh          -> Interactive menu
#   ./init.sh --docker  -> Build & run full stack in Docker (Redis + API + Celery)
#   ./init.sh --local   -> Set up virtualenv and run locally
#   ./init.sh --test    -> Run test suite with coverage
# ==============================================================================

set -eo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ------------------------------------------------------------------------------
# Mode 1: Run via Docker (Full Stack)
# ------------------------------------------------------------------------------
run_docker() {
    log_info "Checking Docker installation..."
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH. Please install Docker."
        exit 1
    fi

    log_info "Building and starting Docker stack (Redis + API + Celery Worker)..."
    mkdir -p output
    docker compose up --build
}

# ------------------------------------------------------------------------------
# Mode 2: Run Locally (Host System)
# ------------------------------------------------------------------------------
run_local() {
    log_info "Checking Python 3 installation..."
    if command -v python3 &> /dev/null; then
        PYTHON_BIN="python3"
    elif command -v python &> /dev/null; then
        PYTHON_BIN="python"
    else
        log_error "Python 3 is required but not found in PATH."
        exit 1
    fi

    VENV_DIR="$ROOT_DIR/venv"
    if [ ! -d "$VENV_DIR" ]; then
        log_info "Creating Python virtual environment in $VENV_DIR..."
        "$PYTHON_BIN" -m venv "$VENV_DIR"
    fi

    # Activate virtual environment
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"

    log_info "Installing / upgrading dependencies..."
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    log_success "Dependencies installed."

    # Start Redis
    log_info "Checking Redis status..."
    if command -v docker &> /dev/null; then
        log_info "Starting Redis via docker compose..."
        docker compose up -d redis
    else
        log_warn "Docker not detected. Ensure local Redis is running on localhost:6379."
    fi

    mkdir -p output

    CELERY_PID=""
    cleanup() {
        log_info "Shutting down background workers..."
        if [ -n "$CELERY_PID" ] && kill -0 "$CELERY_PID" 2>/dev/null; then
            kill "$CELERY_PID" 2>/dev/null || true
        fi
        log_success "All processes stopped."
    }
    trap cleanup EXIT INT TERM

    log_info "Starting Celery background worker..."
    celery -A app.celery_app:celery_app worker --loglevel=info &
    CELERY_PID=$!
    log_success "Celery worker started (PID: $CELERY_PID)."

    log_info "Starting FastAPI application server on http://localhost:8000..."
    log_info "API Docs: http://localhost:8000/docs"
    uvicorn app.main:app --reload --port 8000
}

# ------------------------------------------------------------------------------
# Mode 3: Run Tests
# ------------------------------------------------------------------------------
run_tests() {
    VENV_DIR="$ROOT_DIR/venv"
    if [ ! -d "$VENV_DIR" ]; then
        log_info "Virtualenv not found. Initializing..."
        python3 -m venv "$VENV_DIR"
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
        pip install -r requirements.txt --quiet
    else
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
    fi

    log_info "Running pytest test suite with code coverage..."
    pytest --cov=app --cov-report=term-missing -v
}

# ------------------------------------------------------------------------------
# Entrypoint Dispatcher
# ------------------------------------------------------------------------------
case "$1" in
    --docker|-d)
        run_docker
        ;;
    --local|-l)
        run_local
        ;;
    --test|-t)
        run_tests
        ;;
    *)
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}  Bulk Certificate Generator Runner     ${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo "Choose how you want to run the project:"
        echo "  1) Docker Stack (Redis + FastAPI + Celery in containers) [Recommended]"
        echo "  2) Local Environment (Python venv + local background worker)"
        echo "  3) Run Test Suite (pytest with coverage)"
        echo "  4) Exit"
        echo ""
        read -rp "Enter choice [1-4]: " choice
        case "$choice" in
            1) run_docker ;;
            2) run_local ;;
            3) run_tests ;;
            *) echo "Exiting." ; exit 0 ;;
        esac
        ;;
esac
