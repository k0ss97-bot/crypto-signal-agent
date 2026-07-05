# Перенос Crypto Signal Agent на сервер

Инструкция рассчитана на обычный Linux-сервер, например Ubuntu.

## 1. На Mac: создать архив

Из папки проекта:

```bash
bash deploy/make_deploy_archive.sh
```

Будет создан файл:

```text
deploy/crypto-signal-agent.tar.gz
```

Важно: архив включает `.env`, значит внутри есть ключи OpenAI и Telegram. Не отправляйте этот архив никому.

## 2. На Mac: отправить архив на сервер

Замените `USER` и `SERVER_IP` на свои данные:

```bash
scp deploy/crypto-signal-agent.tar.gz USER@SERVER_IP:~/
```

Или одной командой:

```bash
bash deploy/upload_to_server.sh USER@SERVER_IP
```

## 3. На сервере: распаковать

```bash
ssh USER@SERVER_IP
mkdir -p ~/crypto-signal-agent
tar -xzf ~/crypto-signal-agent.tar.gz -C ~/crypto-signal-agent
cd ~/crypto-signal-agent
```

## 4. На сервере: подготовить Python

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m unittest
```

Если `python3 -m venv` не работает на Ubuntu:

```bash
sudo apt update
sudo apt install -y python3-venv
```

## 5. На сервере: первый запуск мониторинга

Первый запуск сохраняет текущие Bybit Spot пары как уже известные:

```bash
python -m crypto_signal_agent.cli monitor-new --send-alert --send-empty
```

После этого проверить обычный мониторинг:

```bash
python -m crypto_signal_agent.cli monitor-new --send-alert --send-empty
```

Если новых монет нет, это нормально.

## 6. На сервере: включить постоянный запуск через systemd

Самый простой способ:

```bash
bash deploy/install_systemd.sh
```

Проверить статус:

```bash
sudo systemctl status crypto-signal-agent
```

Смотреть логи:

```bash
journalctl -u crypto-signal-agent -f
```

Ручной способ:

Узнайте путь и пользователя:

```bash
pwd
whoami
```

Откройте шаблон:

```bash
nano deploy/crypto-signal-agent.service.template
```

Замените:

```text
/home/USER/crypto-signal-agent
```

на реальный путь, который показал `pwd`.

Затем установите service:

```bash
sudo cp deploy/crypto-signal-agent.service.template /etc/systemd/system/crypto-signal-agent.service
sudo systemctl daemon-reload
sudo systemctl enable crypto-signal-agent
sudo systemctl start crypto-signal-agent
```

Проверить статус:

```bash
sudo systemctl status crypto-signal-agent
```

Смотреть логи:

```bash
journalctl -u crypto-signal-agent -f
```

Остановить:

```bash
sudo systemctl stop crypto-signal-agent
```

## 7. Как это работает на сервере

Сервис запускает:

```bash
python -m crypto_signal_agent.cli monitor-new --loop --send-alert
```

Интервал проверки берется из `.env`:

```text
MONITOR_INTERVAL_SECONDS=300
```

То есть бот проверяет Bybit Spot каждые 5 минут. Если появляется новая `USDT` пара, он проверяет Binance и отправляет сигнал в Telegram.
