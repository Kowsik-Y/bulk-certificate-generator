# Direct one-command runner to build and start the Docker container stack (PowerShell)
$ErrorActionPreference = "Stop"
if (-not (Test-Path "output")) {
    New-Item -ItemType Directory -Path "output" | Out-Null
}
Write-Host "Starting Bulk Certificate Generator Docker Stack..." -ForegroundColor Green
docker compose up --build
