#!/usr/bin/env bash
# Полное удаление SMDG со VPS. Запускать на сервере: bash scripts/remove-smdg.sh
set -euo pipefail

echo "=== Остановка контейнеров SMDG ==="
docker ps -a --format '{{.Names}}' | grep -E '^smdg' | xargs -r docker stop || true
docker ps -a --format '{{.Names}}' | grep -E '^smdg' | xargs -r docker rm -f || true

echo "=== Удаление volumes SMDG ==="
docker volume ls -q | grep -E '^smdg' | xargs -r docker volume rm || true

echo "=== Удаление сети SMDG ==="
docker network rm smdg_backend 2>/dev/null || true

echo "=== Очистка временных compose-файлов ==="
rm -f /tmp/smdg-compose*.yml 2>/dev/null || true

echo "=== Оставшиеся контейнеры ==="
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo "=== SMDG удалён ==="
