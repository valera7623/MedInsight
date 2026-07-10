#!/usr/bin/env bash
set -euo pipefail

echo "Celery beat starting (schema init handled by deploy/app startup)..."
exec celery -A app.tasks.celery_app beat --loglevel=info
