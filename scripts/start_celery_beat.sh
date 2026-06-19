#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/data

echo "Initializing database for Celery beat..."
python -c "
from app.database import Base, bootstrap_system, engine, run_migrations
Base.metadata.create_all(bind=engine)
run_migrations()
bootstrap_system()
print('Database ready')
"

exec celery -A app.tasks.celery_app beat --loglevel=info
