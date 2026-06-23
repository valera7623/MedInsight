#!/usr/bin/env bash
# Fix Docker/git DNS failures caused by systemd-resolved stub (127.0.0.53).
#
# Docker pull and git use the host resolver (/etc/resolv.conf). The stub at
# 127.0.0.53 often returns "server misbehaving" even when dig @8.8.8.8 works.
# daemon.json "dns" only affects containers — not the daemon's own registry pulls.
#
# Run on the VPS with sudo:
#   sudo bash scripts/fix-vps-dns.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

RESOLVED_DROPIN="/etc/systemd/resolved.conf.d/99-medinsight-dns.conf"
DAEMON_JSON="/etc/docker/daemon.json"

echo "→ Configuring systemd-resolved (disable stub listener)..."
mkdir -p /etc/systemd/resolved.conf.d
cat >"$RESOLVED_DROPIN" <<'EOF'
[Resolve]
DNS=8.8.8.8 1.1.1.1 85.193.93.194 85.193.93.193
FallbackDNS=1.0.0.1
DNSStubListener=no
EOF

echo "→ Pointing /etc/resolv.conf at systemd full resolver (not 127.0.0.53 stub)..."
ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf

systemctl restart systemd-resolved

# Ensure eth0 uses public DNS (provider DNS as fallback).
IFACE="$(ip route show default 2>/dev/null | awk '{print $5; exit}')"
if [ -n "${IFACE:-}" ]; then
  resolvectl dns "$IFACE" 8.8.8.8 1.1.1.1 85.193.93.194 85.193.93.193 || true
  resolvectl domain "$IFACE" "~." || true
fi

echo "→ Updating Docker daemon.json (container DNS)..."
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
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        pass
data["dns"] = ["8.8.8.8", "1.1.1.1", "85.193.93.194"]
path.write_text(json.dumps(data, indent=2) + "\n")
print("Updated", path)
PY

systemctl restart docker
sleep 2

echo ""
echo "=== Verification ==="
echo -n "resolv.conf: "; head -1 /etc/resolv.conf
getent hosts github.com >/dev/null && echo "✓ getent github.com" || echo "✗ getent github.com FAILED"
getent hosts registry-1.docker.io >/dev/null && echo "✓ getent registry-1.docker.io" || echo "✗ getent registry-1.docker.io FAILED"
if docker pull hello-world >/dev/null 2>&1; then
  echo "✓ docker pull hello-world"
  docker rmi hello-world >/dev/null 2>&1 || true
else
  echo "✗ docker pull hello-world FAILED — check: cat /etc/resolv.conf && resolvectl status"
  exit 1
fi

echo ""
echo "DNS fix applied. Retry: ./deploy.sh production"
