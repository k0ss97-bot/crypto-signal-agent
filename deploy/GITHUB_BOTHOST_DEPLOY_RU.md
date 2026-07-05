# GitHub + Bothost

Цель: загрузить код на GitHub и подключить репозиторий в Bothost.

## Важно про секреты

Файл `.env` нельзя загружать в GitHub. Он уже добавлен в `.gitignore`.

В Bothost значения из `.env` нужно добавить в разделе переменных окружения:

```text
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.5
QUOTE_ASSET=USDT
PRIMARY_EXCHANGE=bybit
REQUIRED_EXCHANGES=bybit,binance
REQUIRE_ALL_EXCHANGES=true
SCAN_ASSETS=BTC,ETH,SOL,BNB,XRP
MONITOR_INTERVAL_SECONDS=300
BINANCE_BASE_URL=https://api.binance.com
BYBIT_BASE_URL=https://api.bybit.com
DATABASE_PATH=data/signals.sqlite3
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
MAX_SPREAD_PCT=0.35
MIN_VOLUME_RATIO_VS_7D=1.0
MIN_LIQUIDITY_OK=true
NO_SIGNAL_IF_SOURCE_UNVERIFIED=true
LIVE_TRADING_ENABLED=false
```

## Загрузка в GitHub

Если репозиторий уже создан на GitHub, выполните:

```bash
git remote add origin GITHUB_REPO_URL
git push -u origin main
```

Пример:

```bash
git remote add origin git@github.com:USER/crypto-signal-agent.git
git push -u origin main
```

Если используете HTTPS:

```bash
git remote add origin https://github.com/USER/crypto-signal-agent.git
git push -u origin main
```

## Подключение в Bothost

По информации на сайте Bothost:

- поддерживается GitHub/GitLab deploy;
- поддерживаются Docker-контейнеры;
- поддерживаются переменные окружения;
- при пуше в ветку бот может пересобираться и перезапускаться.

Шаги:

1. Зайдите на https://bothost.ru/
2. Зарегистрируйтесь или войдите.
3. Создайте новый проект/бот.
4. Выберите деплой из GitHub.
5. Подключите репозиторий `crypto-signal-agent`.
6. В качестве ветки выберите `main`.
7. Если есть выбор способа сборки, выберите Dockerfile.
8. Добавьте переменные окружения из списка выше.
9. Запустите deploy.
10. Откройте логи и проверьте, что бот пишет:

```text
Мониторинг запущен. Интервал: 300 секунд.
```

## Как бот запускается на Bothost

В репозитории есть `Dockerfile`. Он запускает:

```bash
python -m crypto_signal_agent.cli monitor-new --loop --send-alert
```

Логика:

- бот каждые `MONITOR_INTERVAL_SECONDS` секунд проверяет все Bybit Spot `USDT` пары;
- при первом запуске сохраняет текущие пары как известные;
- если появляется новая пара, проверяет Binance;
- отправляет сигнал в Telegram.

## Важное про хранение базы

База SQLite хранится в:

```text
data/signals.sqlite3
```

Если на тарифе Bothost нет постоянного диска, база может сбрасываться при redeploy/restart. Это не опасно для денег, но бот снова инициализирует список известных пар. Для стабильной работы лучше тариф/настройка с persistent volume.
