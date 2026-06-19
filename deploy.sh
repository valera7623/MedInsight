#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f .env ]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
  echo "Update SECRET_KEY in .env before production use!"
fi

mkdir -p storage

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
  docker compose "${COMPOSE_FILES[@]}" up -d --build app
  APP_PORT="8000"
else
  echo "Starting MedInsight (development)..."
  docker compose "${COMPOSE_FILES[@]}" up -d --build app
  APP_PORT="8000"
fi

echo ""
echo "MedInsight is running."
echo "  Health:     http://localhost:${APP_PORT}/health"
echo "  Dashboard:  http://localhost:${APP_PORT}/"
echo "  Login:      http://localhost:${APP_PORT}/login"
echo "  HTTP (80):  http://localhost/"
echo "  API Docs:   http://localhost:${APP_PORT}/docs"
echo ""
echo "Logs: docker compose ${COMPOSE_FILES[*]} logs -f app"
