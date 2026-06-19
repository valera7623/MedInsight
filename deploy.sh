#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f .env ]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
  echo "Update SECRET_KEY and OPENAI_API_KEY in .env before production use!"
fi

mkdir -p storage secrets

# Docker: app + celery must share the same SQLite file
if grep -q '^DATABASE_URL=' .env; then
  sed -i 's|^DATABASE_URL=.*|DATABASE_URL=sqlite:////app/data/medinsight.db|' .env
else
  echo "DATABASE_URL=sqlite:////app/data/medinsight.db" >> .env
fi

MODE="${1:-dev}"
COMPOSE_FILES=(-f docker-compose.yml)

if [ "$MODE" = "production" ]; then
  COMPOSE_FILES+=(-f docker-compose.prod.yml)
  if grep -q '^APP_PORT=' .env; then
    sed -i 's|^APP_PORT=.*|APP_PORT=8000|' .env
  else
    echo "APP_PORT=8000" >> .env
  fi
  echo "Starting MedInsight (production)..."
  docker stop medinsight-traefik 2>/dev/null || true
  docker rm medinsight-traefik 2>/dev/null || true
else
  echo "Starting MedInsight (development)..."
fi

echo "Rebuilding and restarting containers (spaCy model skipped for fast build)..."
docker compose "${COMPOSE_FILES[@]}" down
docker compose "${COMPOSE_FILES[@]}" build --build-arg INSTALL_SPACY_MODEL=0
docker compose "${COMPOSE_FILES[@]}" up -d redis app celery_worker celery_beat

echo "Waiting for app startup..."
sleep 5

echo "Migrating legacy DB if present..."
docker compose "${COMPOSE_FILES[@]}" exec -T app bash -c '
  mkdir -p /app/data
  if [ -f /app/medinsight.db ] && [ ! -f /app/data/medinsight.db ]; then
    cp /app/medinsight.db /app/data/medinsight.db
    echo "Copied legacy /app/medinsight.db -> /app/data/medinsight.db"
  fi
  python -c "
from app.database import Base, bootstrap_system, engine, run_migrations, sqlite_db_path
from app.config import settings
print(\"DB:\", sqlite_db_path(settings.DATABASE_URL))
Base.metadata.create_all(bind=engine)
run_migrations()
bootstrap_system()
print(\"Tables OK\")
"
' || true

APP_PORT="8000"

echo ""
echo "MedInsight is running."
echo "  Health:     http://localhost:${APP_PORT}/health"
echo "  Dashboard:  http://localhost:${APP_PORT}/"
echo "  Login:      http://localhost:${APP_PORT}/login"
echo "  API Docs:   http://localhost:${APP_PORT}/docs"
echo ""
echo "Verify DB:"
echo "  docker compose ${COMPOSE_FILES[*]} exec app python -c \"from app.database import sqlite_db_path; from app.config import settings; print(sqlite_db_path(settings.DATABASE_URL))\""
echo ""
echo "Logs: docker compose ${COMPOSE_FILES[*]} logs -f app celery_worker"
