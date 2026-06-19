#!/usr/bin/env bash
# Добавьте этот публичный ключ на VPS (один раз, пока вы залогинены по паролю):
#
#   ssh smdg@186.246.3.65
#   mkdir -p ~/.ssh && chmod 700 ~/.ssh
#   echo 'PASTE_PUBKEY_HERE' >> ~/.ssh/authorized_keys
#   chmod 600 ~/.ssh/authorized_keys
#
# После этого с локальной машины:
#   ssh medinsight-vps

set -euo pipefail

PUBKEY_FILE="${HOME}/.ssh/medinsight_deploy.pub"

if [[ ! -f "$PUBKEY_FILE" ]]; then
  echo "Ключ не найден: $PUBKEY_FILE"
  echo "Сгенерируйте: ssh-keygen -t ed25519 -f ~/.ssh/medinsight_deploy -N '' -C medinsight-deploy"
  exit 1
fi

echo "=== Публичный ключ (добавьте на VPS в ~/.ssh/authorized_keys) ==="
cat "$PUBKEY_FILE"
echo ""
echo "=== Команда для VPS ==="
echo "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$(cat "$PUBKEY_FILE")' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
echo ""
echo "=== Проверка с локальной машины ==="
echo "ssh medinsight-vps 'hostname'"
