<#
.SYNOPSIS
    Bulk Certificate Generator - Project Initialization & Runner Script (PowerShell)

.DESCRIPTION
    Initializes and executes the Bulk Certificate Generator in either
    Docker Compose mode (Redis + FastAPI + Celery) or Local host mode.

.PARAMETER Mode
    Execution mode: 'Docker', 'Local', or 'Test'.
    Defaults to interactive prompt if omitted.

.EXAMPLE
    .\init.ps1 -Mode Docker
    .\init.ps1 -Mode Local
    .\init.ps1 -Mode Test
#>

param (
    [ValidateSet("Docker", "Local", "Test", "")]
    [string]$Mode = ""
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Start-DockerStack {
    Write-Step "Checking Docker CLI availability..."
    if (-not (Get-Command "docker" -ErrorAction SilentlyContinue)) {
        Write-Err "Docker is not installed or not in your PATH. Please install Docker Desktop."
        exit 1
    }

    if (-not (Test-Path "output")) {
        New-Item -ItemType Directory -Path "output" | Out-Null
    }

    Write-Step "Building and starting Docker stack (Redis + API + Celery)..."
    docker compose up --build
}

function Start-LocalStack {
    Write-Step "Checking Python installation..."
    $pythonCmd = "python"
    if (-not (Get-Command $pythonCmd -ErrorAction SilentlyContinue)) {
        $pythonCmd = "py"
        if (-not (Get-Command $pythonCmd -ErrorAction SilentlyContinue)) {
            Write-Err "Python 3 is required but was not found. Please install Python 3.11+."
            exit 1
        }
    }

    # Setup Virtual Environment
    $venvPath = Join-Path $PSScriptRoot "venv"
    if (-not (Test-Path $venvPath)) {
        Write-Step "Creating virtual environment in $venvPath..."
        & $pythonCmd -m venv $venvPath
    }

    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    $venvPip = Join-Path $venvPath "Scripts\pip.exe"
    $venvCelery = Join-Path $venvPath "Scripts\celery.exe"
    $venvUvicorn = Join-Path $venvPath "Scripts\uvicorn.exe"

    Write-Step "Installing dependencies from requirements.txt..."
    & $venvPip install --upgrade pip --quiet
    & $venvPip install -r requirements.txt --quiet
    Write-Success "Dependencies installed."

    # Configure Git Hooks
    if ((Test-Path ".git") -and (Test-Path ".husky")) {
        git config core.hooksPath .husky
        Write-Success "Git pre-commit and pre-push hooks activated."
    }

    if (-not (Test-Path "output")) {
        New-Item -ItemType Directory -Path "output" | Out-Null
    }

    # Start Redis and RustFS infrastructure via docker if available
    if (Get-Command "docker" -ErrorAction SilentlyContinue) {
        Write-Step "Starting Redis and RustFS containers..."
        docker compose up -d redis rustfs
    } else {
        Write-Warn "Docker not found. Ensure a local Redis server is listening on localhost:6379."
    }

    Write-Step "Starting Celery background worker in a separate window..."
    Start-Process -FilePath $venvCelery -ArgumentList "-A app.celery_app:celery_app worker --loglevel=info"

    Write-Step "Starting FastAPI server on http://localhost:8000..."
    Write-Success "Interactive Swagger Docs: http://localhost:8000/docs"
    Write-Success "Certificate File Manager: http://localhost:8000/"
    & $venvUvicorn "app.main:app" --reload --port 8000
}

function Run-Tests {
    $venvPath = Join-Path $PSScriptRoot "venv"
    $venvPytest = Join-Path $venvPath "Scripts\pytest.exe"
    $venvRuff = Join-Path $venvPath "Scripts\ruff.exe"
    $venvMypy = Join-Path $venvPath "Scripts\mypy.exe"

    if (-not (Test-Path $venvPytest)) {
        Write-Step "Setting up test environment..."
        & python -m venv $venvPath
        $venvPip = Join-Path $venvPath "Scripts\pip.exe"
        & $venvPip install -r requirements.txt --quiet
    }

    Write-Step "Running test suite with code coverage..."
    & $venvPytest --cov=app --cov-report=term-missing -v

    if (Test-Path $venvRuff) {
        Write-Step "Running Ruff linter..."
        & $venvRuff check app tests
        & $venvRuff format --check app tests
    }

    if (Test-Path $venvMypy) {
        Write-Step "Running Mypy static type checker..."
        & $venvMypy app
    }

    Write-Success "All tests and code quality validations completed!"
}

# Interactive Menu if no mode passed
if ([string]::IsNullOrWhiteSpace($Mode)) {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  Bulk Certificate Generator Runner     " -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "1) Docker Stack (Redis + FastAPI + Celery in containers) [Recommended]"
    Write-Host "2) Local Environment (Python venv + Celery + FastAPI)"
    Write-Host "3) Run Test Suite"
    Write-Host "4) Exit"
    Write-Host ""
    $choice = Read-Host "Enter choice [1-4]"

    switch ($choice) {
        "1" { Start-DockerStack }
        "2" { Start-LocalStack }
        "3" { Run-Tests }
        default { Write-Host "Exiting." ; exit 0 }
    }
} else {
    switch ($Mode.ToLower()) {
        "docker" { Start-DockerStack }
        "local"  { Start-LocalStack }
        "test"   { Run-Tests }
    }
}
