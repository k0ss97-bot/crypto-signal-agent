#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PROJECT_DIR="$(pwd)"
CURRENT_USER="$(id -un)"
SERVICE_TMP="/tmp/crypto-signal-agent.service"

sed \
  -e "s|/home/USER/crypto-signal-agent|${PROJECT_DIR}|g" \
  -e "s|User=USER|User=${CURRENT_USER}|g" \
  deploy/crypto-signal-agent.service.template > "${SERVICE_TMP}"

sudo cp "${SERVICE_TMP}" /etc/systemd/system/crypto-signal-agent.service
sudo systemctl daemon-reload
sudo systemctl enable crypto-signal-agent
sudo systemctl restart crypto-signal-agent

echo "Сервис установлен и запущен."
echo "Статус:"
echo "  sudo systemctl status crypto-signal-agent"
echo "Логи:"
echo "  journalctl -u crypto-signal-agent -f"
