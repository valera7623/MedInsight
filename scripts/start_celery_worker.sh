#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/data

echo "Celery worker starting (schema init handled by deploy/app startup)..."
exec celery -A app.tasks.celery_app worker --loglevel=info
