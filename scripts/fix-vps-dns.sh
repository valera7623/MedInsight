#!/usr/bin/env bash
# Fix intermittent Docker DNS failures on VPS (systemd-resolved 127.0.0.53).
# Run on the VPS with sudo:
#   sudo bash scripts/fix-vps-dns.sh
set -euo pipefail

DAEMON_JSON="/etc/docker/daemon.json"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

mkdir -p /etc/docker

if [ -f "$DAEMON_JSON" ]; then
  cp "$DAEMON_JSON" "${DAEMON_JSON}.bak.$(date +%s)"
fi

python3 - <<'PY'
import json
from pathlib import Path

path = Path("/etc/docker/daemon.json")
data = {}
if path.exists():
    data = json.loads(path.read_text())
data["dns"] = ["8.8.8.8", "1.1.1.1", "85.193.93.194"]
path.write_text(json.dumps(data, indent=2) + "\n")
print("Updated", path)
PY

systemctl restart docker
echo "Docker restarted. Test: docker pull hello-world"
