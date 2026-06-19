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
  echo "Starting MedInsight (production: app + Traefik)..."
  docker compose "${COMPOSE_FILES[@]}" --profile production up -d --build
  APP_PORT="$(grep -E '^APP_PORT=' .env | cut -d= -f2 || echo 8000)"
else
  echo "Starting MedInsight (development)..."
  docker compose "${COMPOSE_FILES[@]}" up -d --build app
  APP_PORT="8000"
fi

echo ""
echo "MedInsight is running."
  echo "  Health:     http://localhost:${APP_PORT}/health"
  echo "  Dashboard:  http://localhost:${APP_PORT}/"
  echo "  HTTPS:      https://${DOMAIN:-localhost}/ (Traefik, if DOMAIN configured)"
echo "  Login:      http://localhost:${APP_PORT}/login"
echo "  API Docs:   http://localhost:${APP_PORT}/docs"
echo ""
echo "Logs: docker compose ${COMPOSE_FILES[*]} logs -f app"
