#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f .env ]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
  echo "Update SECRET_KEY, POSTGRES_PASSWORD and OPENAI_API_KEY in .env before production use!"
fi

mkdir -p storage secrets

MODE="${1:-dev}"
COMPOSE_FILES=(-f docker-compose.yml)
PROFILE_ARGS=()

if [ "$MODE" = "production" ]; then
  COMPOSE_FILES+=(-f docker-compose.prod.yml)
  PROFILE_ARGS=(--profile production)
  PG_URL="${PRODUCTION_DATABASE_URL:-postgresql://medinsight:secure_password@postgres:5432/medinsight}"
  if grep -q '^DATABASE_URL=' .env; then
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${PG_URL}|" .env
  else
    echo "DATABASE_URL=${PG_URL}" >> .env
  fi
  if grep -q '^PRODUCTION_DATABASE_URL=' .env; then
    sed -i "s|^PRODUCTION_DATABASE_URL=.*|PRODUCTION_DATABASE_URL=${PG_URL}|" .env
  else
    echo "PRODUCTION_DATABASE_URL=${PG_URL}" >> .env
  fi
  if grep -q '^APP_PORT=' .env; then
    sed -i 's|^APP_PORT=.*|APP_PORT=8000|' .env
  else
    echo "APP_PORT=8000" >> .env
  fi
  echo "Starting MedInsight (production, PostgreSQL + HTTPS via Traefik)..."
else
  SQLITE_URL="${DEVELOPMENT_DATABASE_URL:-sqlite:////app/data/medinsight.db}"
  if grep -q '^DATABASE_URL=' .env; then
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${SQLITE_URL}|" .env
  else
    echo "DATABASE_URL=${SQLITE_URL}" >> .env
  fi
  echo "Starting MedInsight (development, SQLite)..."
fi

echo "Rebuilding and restarting containers (spaCy model skipped for fast build)..."
docker compose "${COMPOSE_FILES[@]}" "${PROFILE_ARGS[@]}" down
docker compose "${COMPOSE_FILES[@]}" "${PROFILE_ARGS[@]}" build --build-arg INSTALL_SPACY_MODEL=0
docker compose "${COMPOSE_FILES[@]}" "${PROFILE_ARGS[@]}" up -d

if [ "$MODE" = "production" ] && [ -x scripts/docker_cleanup.sh ]; then
  echo "Pruning stopped containers and unused images from previous builds..."
  bash scripts/docker_cleanup.sh deploy
fi

echo "Waiting for app startup..."
sleep 8

echo "Initializing database schema..."
docker compose "${COMPOSE_FILES[@]}" exec -T app bash -c '
  python -c "
from app.core.database import Base, bootstrap_system, engine, is_postgresql, is_sqlite, run_migrations, sqlite_db_path
from app.config import settings
if is_sqlite():
    import os
    os.makedirs(\"/app/data\", exist_ok=True)
    if os.path.isfile(\"/app/medinsight.db\") and not os.path.isfile(\"/app/data/medinsight.db\"):
        import shutil
        shutil.copy2(\"/app/medinsight.db\", \"/app/data/medinsight.db\")
        print(\"Copied legacy SQLite DB to /app/data/\")
    print(\"DB:\", sqlite_db_path(settings.DATABASE_URL))
elif is_postgresql():
    print(\"DB: PostgreSQL\", settings.DATABASE_URL.split(\"@\")[-1])
Base.metadata.create_all(bind=engine)
run_migrations()
bootstrap_system()
print(\"Tables OK\")
"
' || true

if [ "$MODE" = "production" ]; then
  echo ""
  echo "Optional: migrate existing SQLite data to PostgreSQL:"
  echo "  docker compose ${COMPOSE_FILES[*]} exec app python scripts/migrate_to_postgres.py \\"
  echo "    --sqlite-url sqlite:////app/data/medinsight.db \\"
  echo "    --postgres-url \"\${PRODUCTION_DATABASE_URL}\""
fi

APP_PORT="8000"

echo ""
echo "MedInsight is running."
echo "  Health:     http://localhost:${APP_PORT}/health"
echo "  Dashboard:  http://localhost:${APP_PORT}/"
echo "  Login:      http://localhost:${APP_PORT}/login"
echo "  API Docs:   http://localhost:${APP_PORT}/docs"
echo "  Help Docs:  http://localhost:${APP_PORT}/help/"
echo ""
if [ "$MODE" = "production" ]; then
  echo "Verify PostgreSQL:"
  echo "  docker compose ${COMPOSE_FILES[*]} exec app python scripts/test_postgres.py"
else
  echo "Verify SQLite:"
  echo "  docker compose ${COMPOSE_FILES[*]} exec app python -c \"from app.database import sqlite_db_path; from app.config import settings; print(sqlite_db_path(settings.DATABASE_URL))\""
fi
echo ""
echo "Logs: docker compose ${COMPOSE_FILES[*]} logs -f app celery_worker"
