# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code and project metadata
COPY app/ ./app/
COPY pyproject.toml README.md ./

# Create data directories for SQLite database and generated PDF certificates
RUN mkdir -p /data/output && chmod -R 777 /data

# Default environment configuration for Docker stack
ENV DATABASE_URL="sqlite:////data/certificates.db" \
    OUTPUT_DIR="/data/output" \
    REDIS_URL="redis://redis:6379/0"

EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command: FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

