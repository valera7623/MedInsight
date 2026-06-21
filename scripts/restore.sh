#!/usr/bin/env bash
#
# Restore MedInsight from a backup archive.
#
# Usage:
#   ./scripts/restore.sh /path/to/backup_<ts>.tar.gz          # full backup
#   ./scripts/restore.sh /path/to/backup_<ts>.db.gz           # db-only
#   ./scripts/restore.sh /path/to/backup_<ts>.storage.tar.gz  # storage-only
#
# For full/storage restores under Docker it stops the app/celery containers
# first and restarts them afterwards. A safety copy of the current DB and
# storage is made (*.pre-restore) before overwriting.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

BACKUP_FILE="${1:-}"
if [ -z "$BACKUP_FILE" ] || [ ! -f "$BACKUP_FILE" ]; then
  echo "Usage: $0 /path/to/backup.(tar.gz|db.gz|storage.tar.gz)" >&2
  exit 1
fi

if [ -f .env ]; then
  set -a; . ./.env; set +a
fi
STORAGE_PATH="${STORAGE_PATH:-./storage}"
DATABASE_URL="${DATABASE_URL:-sqlite:///./medinsight.db}"
DB_PATH="${DATABASE_URL#sqlite:///}"

read -r -p "⚠️  This will OVERWRITE current data. Continue? [y/N] " ans
[ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "Aborted."; exit 1; }

USE_DOCKER=0
if command -v docker >/dev/null 2>&1 && docker compose ps >/dev/null 2>&1; then
  USE_DOCKER=1
fi

stop_app() {
  if [ "$USE_DOCKER" = "1" ]; then
    echo "→ Stopping app & celery containers…"
    docker compose stop app celery_worker celery_beat 2>/dev/null || true
  fi
}
start_app() {
  if [ "$USE_DOCKER" = "1" ]; then
    echo "→ Starting containers…"
    docker compose start app celery_worker celery_beat 2>/dev/null || true
  fi
}

restore_db_file() {
  local src="$1"
  [ -f "$DB_PATH" ] && cp "$DB_PATH" "${DB_PATH}.pre-restore"
  echo "→ Restoring DB → $DB_PATH"
  gunzip -c "$src" > "$DB_PATH"
}

restore_storage_dir() {
  local extracted="$1"  # directory that contains a 'storage' folder
  if [ -d "$extracted/storage" ]; then
    [ -d "$STORAGE_PATH" ] && rm -rf "${STORAGE_PATH}.pre-restore" && mv "$STORAGE_PATH" "${STORAGE_PATH}.pre-restore"
    echo "→ Restoring storage → $STORAGE_PATH"
    cp -r "$extracted/storage" "$STORAGE_PATH"
    mkdir -p "$STORAGE_PATH/exports"
  fi
}

stop_app

case "$BACKUP_FILE" in
  *.storage.tar.gz)
    TMP="$(mktemp -d)"; tar -xzf "$BACKUP_FILE" -C "$TMP"; restore_storage_dir "$TMP"; rm -rf "$TMP"
    ;;
  *.db.gz)
    restore_db_file "$BACKUP_FILE"
    ;;
  *.tar.gz)
    TMP="$(mktemp -d)"; tar -xzf "$BACKUP_FILE" -C "$TMP"
    ROOT="$TMP/backup"; [ -d "$ROOT" ] || ROOT="$TMP"
    if [ -f "$ROOT/medinsight.db" ]; then
      [ -f "$DB_PATH" ] && cp "$DB_PATH" "${DB_PATH}.pre-restore"
      echo "→ Restoring DB → $DB_PATH"
      cp "$ROOT/medinsight.db" "$DB_PATH"
    fi
    restore_storage_dir "$ROOT"
    rm -rf "$TMP"
    ;;
  *)
    echo "Unknown backup format: $BACKUP_FILE" >&2; start_app; exit 1 ;;
esac

start_app
echo "✓ Restore complete from: $BACKUP_FILE"
