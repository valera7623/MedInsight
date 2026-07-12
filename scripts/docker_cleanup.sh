#!/usr/bin/env bash
# Safe Docker cleanup for MedInsight VPS.
# Never removes named volumes (medinsight-data, chroma, backups, traefik certs).
#
# Usage:
#   ./scripts/docker_cleanup.sh deploy   # after each production deploy (light)
#   ./scripts/docker_cleanup.sh weekly   # cron: images + build cache (default)

set -euo pipefail

MODE="${1:-weekly}"

log() {
  echo "[docker-cleanup] $(date -Is) $*"
}

log "Mode: ${MODE}"

before=$(docker system df --format '{{.Type}}\t{{.Size}}' 2>/dev/null || true)

log "Removing stopped containers..."
docker container prune -f

log "Removing unused images (running containers are kept)..."
docker image prune -f

if [ "$MODE" = "weekly" ] || [ "$MODE" = "full" ]; then
  log "Pruning build cache older than 7 days..."
  docker builder prune -f --filter until=168h
fi

log "Disk usage after cleanup:"
if docker system df 2>/dev/null; then
  :
else
  log "Warning: docker system df failed (containerd snapshot metadata); cleanup succeeded."
  df -h /var/lib/docker 2>/dev/null || df -h /
fi

if [ -n "$before" ]; then
  log "Cleanup complete."
fi
