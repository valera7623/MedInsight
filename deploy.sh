#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Stable compose project name (avoids orphan containers after path/profile changes).
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-medinsight}"

remove_stale_medinsight_containers() {
  # Only remove production-named containers — never touch medinsight-demo-*.
  local ids
  ids="$(
    docker ps -aq --filter "name=^medinsight-" 2>/dev/null \
      | while read -r id; do
          [ -z "$id" ] && continue
          name="$(docker inspect -f '{{.Name}}' "$id" 2>/dev/null | sed 's#^/##')"
          case "$name" in
            medinsight-demo-*) ;;
            *) echo "$id" ;;
          esac
        done
  )"
  if [ -n "$ids" ]; then
    echo "Removing stale medinsight containers from a previous deploy..."
    # shellcheck disable=SC2086
    docker rm -f $ids >/dev/null 2>&1 || true
  fi
}

compose() {
  docker compose "${COMPOSE_FILES[@]}" "${PROFILE_ARGS[@]}" "$@"
}

MODE="${1:-dev}"

# ---------------------------------------------------------------------------
# Demo stack (separate project + DB; shares Traefik network with production)
# ---------------------------------------------------------------------------
if [ "$MODE" = "demo" ]; then
  export COMPOSE_PROJECT_NAME=medinsight-demo
  COMPOSE_FILES=(-f docker-compose.demo.yml)
  PROFILE_ARGS=()

  if [ -d .git ]; then
    echo "Pulling latest code from origin/main..."
    if ! git fetch origin main; then
      echo "WARNING: git fetch failed (DNS?) — continuing with current checkout" >&2
    elif ! git merge --ff-only origin/main; then
      echo "WARNING: fast-forward failed — run 'git pull --rebase origin main' manually" >&2
    fi
  fi

  if [ ! -f .env.demo ]; then
    echo "Creating .env.demo from .env.demo.example..."
    cp .env.demo.example .env.demo
  fi
  # Prefer a real SECRET_KEY from production .env when present.
  if [ -f .env ] && grep -q '^SECRET_KEY=' .env; then
    _sk="$(grep '^SECRET_KEY=' .env | head -1 | cut -d= -f2-)"
    if [ -n "$_sk" ] && [ "$_sk" != "change-me-demo-secret-key" ]; then
      if grep -q '^SECRET_KEY=' .env.demo; then
        sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${_sk}|" .env.demo
      else
        echo "SECRET_KEY=${_sk}" >> .env.demo
      fi
    fi
  fi
  mkdir -p demo_storage secrets demo_data/dicom
  if [ ! -f secrets/encryption_key.txt ]; then
    echo "NOTE: secrets/encryption_key.txt missing — bootstrap will create one on first run"
  fi

  # Ensure Traefik shared network exists (created by production stack).
  if ! docker network inspect medinsight_medinsight-net >/dev/null 2>&1; then
    echo "ERROR: network medinsight_medinsight-net not found."
    echo "Start production first (./deploy.sh production) so Traefik can route demo.fileguardian.com.ru"
    exit 1
  fi

  echo "Generating demo DICOM sample pack if needed..."
  if command -v python3 >/dev/null 2>&1; then
    PYTHONPATH=. python3 -m scripts.generate_demo_dicom || true
  fi

  echo "Starting MedInsight DEMO (PostgreSQL + DEMO_MODE=true)..."
  BUILD_ARGS=(--build-arg INSTALL_SPACY_MODEL=0 --build-arg BUILD_DOCS=0)
  if ! docker image inspect medinsight-app:latest >/dev/null 2>&1; then
    echo "Building app image for demo..."
    compose build "${BUILD_ARGS[@]}" demo_app
  fi
  # Recreate app if a previous attempt left it unhealthy / half-migrated.
  compose up -d --build --force-recreate demo_postgres demo_redis demo_app || {
    echo "ERROR: demo_app failed to start. Recent logs:" >&2
    compose logs --tail 80 demo_app || true
    exit 1
  }
  compose up -d demo_celery || true

  echo "Waiting for demo app to become healthy..."
  for i in $(seq 1 40); do
    if compose exec -T demo_app curl -sf http://localhost:8000/health/live >/dev/null 2>&1; then
      echo "Demo app is healthy."
      break
    fi
    if [ "$i" -eq 40 ]; then
      echo "ERROR: demo_app health check timed out. Logs:" >&2
      compose logs --tail 100 demo_app || true
      exit 1
    fi
    sleep 3
  done

  echo "Initializing demo database schema..."
  compose exec -T demo_app bash -c '
    python -c "
from app.core.database import Base, bootstrap_system, engine, run_migrations
Base.metadata.create_all(bind=engine)
run_migrations()
bootstrap_system()
print(\"Tables OK\")
"
  '

  echo "Seeding demo data..."
  compose exec -T demo_app bash -c 'PYTHONPATH=/app python -m scripts.seed_demo' || {
    echo "Seed failed once — retrying with --force..."
    compose exec -T demo_app bash -c 'PYTHONPATH=/app python -m scripts.seed_demo --force'
  }

  echo ""
  echo "MedInsight DEMO is running."
  echo "  Local:       http://localhost:${DEMO_APP_PORT:-8001}/"
  echo "  Public:      https://demo.fileguardian.com.ru/demo"
  echo "  Login:       https://demo.fileguardian.com.ru/demo/login"
  echo "  Credentials: demo@medinsight.com / demo123 (clinic-1)"
  echo ""
  echo "DNS: ensure A-record demo.fileguardian.com.ru → VPS IP"
  echo "Logs: docker compose -f docker-compose.demo.yml -p medinsight-demo logs -f demo_app"
  exit 0
fi

if [ ! -f .env ]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
  echo "Update SECRET_KEY, POSTGRES_PASSWORD and OPENAI_API_KEY in .env before production use!"
fi

mkdir -p storage secrets

COMPOSE_FILES=(-f docker-compose.yml)
PROFILE_ARGS=()

if [ -d .git ]; then
  echo "Pulling latest code from origin/main..."
  if ! git fetch origin main; then
    echo "WARNING: git fetch failed (DNS?) — continuing with current checkout" >&2
  elif ! git merge --ff-only origin/main; then
    echo "WARNING: fast-forward failed — run 'git pull --rebase origin main' manually" >&2
  fi
fi

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
  for key_val in \
    "OTEL_ENABLED=false" \
    "CHROMA_EMBEDDINGS_ENABLED=false"; do
    key="${key_val%%=*}"
    val="${key_val#*=}"
    if grep -q "^${key}=" .env; then
      sed -i "s|^${key}=.*|${key}=${val}|" .env
    else
      echo "${key}=${val}" >> .env
    fi
  done
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
compose down --remove-orphans 2>/dev/null || true
remove_stale_medinsight_containers

BUILD_ARGS=(--build-arg INSTALL_SPACY_MODEL=0 --build-arg BUILD_DOCS=0)
echo "Building app image once (pre-built site/ for /help/, shared by celery/telegram)..."
compose build "${BUILD_ARGS[@]}" app
compose up -d

if [ "$MODE" = "production" ] && [ -x scripts/docker_cleanup.sh ]; then
  echo "Pruning stopped containers and unused images from previous builds..."
  bash scripts/docker_cleanup.sh deploy
fi

echo "Waiting for app startup..."
sleep 8

echo "Initializing database schema..."
compose exec -T app bash -c '
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
