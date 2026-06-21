#!/usr/bin/env bash
# Configure or resize swap on Ubuntu VPS (MedInsight / Docker).
#
# Recommended for 2 GB RAM hosts: 4 GB swap, swappiness=10.
#
# Run on VPS as root:
#   sudo SWAP_SIZE_GB=4 SWAPPINESS=10 ./scripts/setup_swap.sh
#
# Idempotent: safe to re-run; resizes /swapfile if size differs.

set -euo pipefail

SWAP_SIZE_GB="${SWAP_SIZE_GB:-4}"
SWAPPINESS="${SWAPPINESS:-10}"
SWAPFILE="${SWAPFILE:-/swapfile}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo $0"
  exit 1
fi

if ! [[ "$SWAP_SIZE_GB" =~ ^[0-9]+$ ]] || [ "$SWAP_SIZE_GB" -lt 1 ]; then
  echo "SWAP_SIZE_GB must be a positive integer (got: $SWAP_SIZE_GB)"
  exit 1
fi

target_bytes=$((SWAP_SIZE_GB * 1024 * 1024 * 1024))
need_create=1

if [ -f "$SWAPFILE" ]; then
  current_bytes=$(stat -c%s "$SWAPFILE")
  if [ "$current_bytes" -eq "$target_bytes" ]; then
    echo "Swap file already ${SWAP_SIZE_GB}G at $SWAPFILE"
    need_create=0
  else
    echo "Resizing swap: $((current_bytes / 1024 / 1024 / 1024))G -> ${SWAP_SIZE_GB}G"
    if swapon --show | grep -qF "$SWAPFILE"; then
      echo "Disabling swap temporarily..."
      swapoff "$SWAPFILE"
    fi
    rm -f "$SWAPFILE"
  fi
fi

if [ "$need_create" -eq 1 ]; then
  echo "Creating ${SWAP_SIZE_GB}G swap file at $SWAPFILE ..."
  if fallocate -l "${SWAP_SIZE_GB}G" "$SWAPFILE" 2>/dev/null; then
    :
  else
    echo "fallocate failed, using dd (slower)..."
    dd if=/dev/zero of="$SWAPFILE" bs=1M count=$((SWAP_SIZE_GB * 1024)) status=progress
  fi
  chmod 600 "$SWAPFILE"
  mkswap "$SWAPFILE"
fi

if ! swapon --show | grep -qF "$SWAPFILE"; then
  swapon "$SWAPFILE"
fi

if ! grep -qF "$SWAPFILE" /etc/fstab; then
  echo "$SWAPFILE none swap sw 0 0" >> /etc/fstab
  echo "Added $SWAPFILE to /etc/fstab"
fi

sysctl_file=/etc/sysctl.d/99-medinsight-swappiness.conf
echo "vm.swappiness=$SWAPPINESS" > "$sysctl_file"
sysctl -p "$sysctl_file" >/dev/null

echo ""
echo "Swap configured:"
swapon --show
free -h
echo "swappiness=$(cat /proc/sys/vm/swappiness)"
