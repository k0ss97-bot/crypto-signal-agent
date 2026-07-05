# Crypto Signal Agent MVP

Локальный MVP для анализа крипто-событий. Агент проверяет, можно ли торговать монетой на нужных биржах, считает оценку события, применяет риск-фильтр, сохраняет сигналы в SQLite и может отправлять уведомления в Telegram.

Эта версия не размещает реальные ордера.

## Торговое правило

Правило по умолчанию:

- Bybit Spot — основная обязательная биржа.
- Binance Spot — обязательное подтверждение по умолчанию.
- Базовая котировка — `USDT`.

Это значит, что `ABC` считается торгуемой монетой только если пара `ABCUSDT` есть и на Bybit Spot, и на Binance Spot.

Чтобы перейти в режим Bybit-only, укажите:

```text
PRIMARY_EXCHANGE=bybit
REQUIRED_EXCHANGES=bybit,binance
REQUIRE_ALL_EXCHANGES=false
```

В таком режиме отсутствие Binance станет предупреждением, но отсутствие Bybit все равно заблокирует сигнал.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

На текущем этапе `pip install -e .` не обязателен: из папки проекта команды `python -m crypto_signal_agent.cli ...` работают напрямую.

Если хотите установить пакет в окружение, используйте:

```bash
pip install -e .
```

Для анализа через OpenAI дополнительно понадобится:

```bash
pip install -e ".[openai]"
```

Заполните `.env`. Для MVP используйте только read-only ключи бирж, если они понадобятся. Live trading специально отключен.

## Демо без сети

```bash
python -m crypto_signal_agent.cli analyze-event \
  --asset ABC \
  --event-type major_cex_spot_listing \
  --source-name Bybit \
  --source-url https://example.com/abc \
  --official \
  --price-change-20m-pct 18 \
  --volume-ratio-vs-7d 6.2 \
  --spread-pct 0.18 \
  --offline-venues bybit,binance
```

## Проверка реальной пары

```bash
python -m crypto_signal_agent.cli check-symbol ABC
```

Команда проверяет пару `ABCUSDT` на Bybit Spot и Binance Spot.

## Самостоятельная проверка списка монет

Список по умолчанию задается в `.env`:

```text
SCAN_ASSETS=BTC,ETH,SOL,BNB,XRP
```

Запуск проверки:

```bash
python -m crypto_signal_agent.cli scan
```

Проверить свой список:

```bash
python -m crypto_signal_agent.cli scan --assets BTC,SOL,LINK
```

Проверить и отправить отчет в Telegram:

```bash
python -m crypto_signal_agent.cli scan --assets BTC,SOL,LINK --send-alert
```

Для демо без сети:

```bash
python -m crypto_signal_agent.cli scan --assets BTC,SOL,LINK --offline-venues bybit,binance
```

## Мониторинг новых монет

Первый запуск сохраняет текущий список Bybit Spot как уже известный, чтобы бот не прислал сотни старых монет:

```bash
python -m crypto_signal_agent.cli monitor-new --send-alert --send-empty
```

После этого обычная разовая проверка:

```bash
python -m crypto_signal_agent.cli monitor-new --send-alert
```

Постоянный мониторинг:

```bash
python -m crypto_signal_agent.cli monitor-new --loop --send-alert
```

Или коротко:

```bash
bash run_monitor.sh
```

Интервал задается в `.env`:

```text
MONITOR_INTERVAL_SECONDS=300
```

При таком запуске бот сам проверяет весь Bybit Spot каждые 5 минут. Если появляется новая `USDT`-пара, он проверяет Binance, формирует сигнал и отправляет его в Telegram. Если новых монет нет, сообщение не отправляется.

## Деплой на Bothost через GitHub

Для Bothost добавлен `Dockerfile`. Он запускает постоянный мониторинг:

```bash
python -m crypto_signal_agent.cli monitor-new --loop --send-alert
```

Инструкция по загрузке в GitHub и подключению Bothost лежит здесь:

```text
deploy/GITHUB_BOTHOST_DEPLOY_RU.md
```

## Тесты

```bash
python -m unittest
```

## Заметки

- Анализ OpenAI необязателен. Если `OPENAI_API_KEY` не указан, агент вернет детерминированное русское резюме.
- Уведомления Telegram необязательны. Если переменные Telegram не заполнены, отправка будет пропущена.
- Риск-фильтр может заблокировать сигнал даже при высокой оценке.
