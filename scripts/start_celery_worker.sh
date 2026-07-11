#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/data

echo "Celery worker starting (schema init handled by deploy/app startup)..."
CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-2}"
exec celery -A app.tasks.celery_app worker --loglevel=info --concurrency="${CONCURRENCY}"
