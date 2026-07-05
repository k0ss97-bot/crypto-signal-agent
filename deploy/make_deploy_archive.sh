#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p deploy

tar \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='*.egg-info' \
  --exclude='deploy/*.tar.gz' \
  -czf deploy/crypto-signal-agent.tar.gz \
  .env .env.example README.md pyproject.toml run_monitor.sh crypto_signal_agent tests outputs deploy/crypto-signal-agent.service.template \
  deploy/SERVER_DEPLOY_RU.md deploy/install_systemd.sh

echo "Готово: deploy/crypto-signal-agent.tar.gz"
echo "Архив включает .env. Храните его аккуратно: внутри есть ключи."
