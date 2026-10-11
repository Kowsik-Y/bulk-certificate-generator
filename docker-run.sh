#!/usr/bin/env bash
# Direct one-command runner to build and start the Docker container stack
set -e
mkdir -p output
echo "Starting Bulk Certificate Generator Docker Stack..."
docker compose up --build
