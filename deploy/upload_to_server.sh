#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Использование: bash deploy/upload_to_server.sh USER@SERVER_IP"
  exit 1
fi

TARGET="$1"

cd "$(dirname "$0")/.."

bash deploy/make_deploy_archive.sh
scp deploy/crypto-signal-agent.tar.gz "$TARGET:~/"

echo
echo "Архив отправлен на сервер: $TARGET:~/crypto-signal-agent.tar.gz"
echo "Дальше зайдите на сервер:"
echo "  ssh $TARGET"
echo "  mkdir -p ~/crypto-signal-agent"
echo "  tar -xzf ~/crypto-signal-agent.tar.gz -C ~/crypto-signal-agent"
echo "  cd ~/crypto-signal-agent"
echo "  python3 -m venv .venv"
echo "  source .venv/bin/activate"
echo "  python -m crypto_signal_agent.cli monitor-new --send-alert --send-empty"
echo "  bash deploy/install_systemd.sh"
