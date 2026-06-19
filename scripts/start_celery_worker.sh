#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/data

echo "Initializing database for Celery worker..."
python -c "
from app.database import Base, bootstrap_system, engine, run_migrations, sqlite_db_path
from app.config import settings
path = sqlite_db_path(settings.DATABASE_URL)
print(f'Database path: {path}')
Base.metadata.create_all(bind=engine)
run_migrations()
bootstrap_system()
print('Database ready')
"

exec celery -A app.tasks.celery_app worker --loglevel=info
