#!/usr/bin/env bash
#
# Manual backup without the running application.
#
# Usage:
#   ./scripts/backup.sh [full|db|storage]      # default: full
#
# Honours BACKUP_DIR / DATABASE_URL / STORAGE_PATH from .env (or environment).
# Output layout (under BACKUP_DIR):
#   full/<id>.tar.gz   db/<id>.db.gz   storage/<id>.storage.tar.gz   metadata/<id>.json
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

TYPE="${1:-full}"

# Load .env if present (without overriding already-set env vars).
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

BACKUP_DIR="${BACKUP_DIR:-./backups}"
STORAGE_PATH="${STORAGE_PATH:-./storage}"
DATABASE_URL="${DATABASE_URL:-sqlite:///./medinsight.db}"
DB_PATH="${DATABASE_URL#sqlite:///}"

TS="$(date +%Y-%m-%d_%H-%M-%S)"
ID="backup_${TS}"

mkdir -p "$BACKUP_DIR"/{full,db,storage,metadata}

backup_db() {
  echo "→ Backing up database: $DB_PATH"
  if [ ! -f "$DB_PATH" ]; then
    echo "  WARNING: DB file not found at $DB_PATH" >&2
    return 1
  fi
  local tmp="$BACKUP_DIR/db/.${ID}.tmp.db"
  # Consistent online snapshot via sqlite3 .backup (falls back to copy).
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DB_PATH" ".backup '$tmp'"
  else
    cp "$DB_PATH" "$tmp"
  fi
  gzip -c "$tmp" > "$BACKUP_DIR/db/${ID}.db.gz"
  rm -f "$tmp"
  echo "  ✓ $BACKUP_DIR/db/${ID}.db.gz"
}

backup_storage() {
  echo "→ Backing up storage: $STORAGE_PATH"
  tar --exclude="*/exports/*" -czf "$BACKUP_DIR/storage/${ID}.storage.tar.gz" \
    -C "$(dirname "$STORAGE_PATH")" "$(basename "$STORAGE_PATH")" 2>/dev/null || \
    tar -czf "$BACKUP_DIR/storage/${ID}.storage.tar.gz" "$STORAGE_PATH"
  echo "  ✓ $BACKUP_DIR/storage/${ID}.storage.tar.gz"
}

backup_full() {
  echo "→ Full backup (db + storage + sanitized config)"
  local stage
  stage="$(mktemp -d)"
  mkdir -p "$stage/backup/config"

  if [ -f "$DB_PATH" ]; then
    if command -v sqlite3 >/dev/null 2>&1; then
      sqlite3 "$DB_PATH" ".backup '$stage/backup/medinsight.db'"
    else
      cp "$DB_PATH" "$stage/backup/medinsight.db"
    fi
  fi

  if [ -d "$STORAGE_PATH" ]; then
    mkdir -p "$stage/backup/storage"
    tar --exclude="*/exports/*" -C "$STORAGE_PATH" -cf - . | tar -C "$stage/backup/storage" -xf -
  fi

  # Sanitized .env (strip secret-looking values).
  if [ -f .env ]; then
    sed -E 's/^([A-Za-z0-9_]*(KEY|PASSWORD|SECRET|TOKEN)[A-Za-z0-9_]*)=.*/\1=__REDACTED__/' .env \
      > "$stage/backup/config/.env"
  fi
  [ -d traefik ] && cp -r traefik "$stage/backup/config/traefik"

  cat > "$stage/backup/metadata.json" <<EOF
{
  "version": "${APP_VERSION:-1.0.0}",
  "backup_id": "${ID}",
  "type": "full",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source": "scripts/backup.sh"
}
EOF
  cp "$stage/backup/metadata.json" "$BACKUP_DIR/metadata/${ID}.json"

  tar -C "$stage" -czf "$BACKUP_DIR/full/${ID}.tar.gz" backup
  rm -rf "$stage"
  echo "  ✓ $BACKUP_DIR/full/${ID}.tar.gz"
}

case "$TYPE" in
  full)    backup_full ;;
  db)      backup_db ;;
  storage) backup_storage ;;
  *) echo "Usage: $0 [full|db|storage]" >&2; exit 1 ;;
esac

echo "Backup ($TYPE) complete: ${ID}"
