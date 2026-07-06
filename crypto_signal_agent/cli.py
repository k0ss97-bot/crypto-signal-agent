from __future__ import annotations

import argparse
import json
import sys
import time

from crypto_signal_agent.alerts.telegram import TelegramAlerter
from crypto_signal_agent.collectors.venues import VenueChecker
from crypto_signal_agent.config import Settings
from crypto_signal_agent.models import Event, MarketMetrics, Source
from crypto_signal_agent.listing_monitor import NewListingMonitor, parse_monitor_exchanges, telegram_status_text
from crypto_signal_agent.pipeline import SignalPipeline
from crypto_signal_agent.presentation import user_signal_dict, user_venue_dict
from crypto_signal_agent.scanner import (
    build_scan_payload,
    evaluate_asset_scan,
    format_scan_message,
    parse_assets,
)
from crypto_signal_agent.storage.sqlite_store import SignalStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crypto-signal-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check-symbol", help="Проверить обязательные спотовые биржи для монеты.")
    check.add_argument("asset", help="Базовая монета, например BTC или SOL.")

    analyze = subparsers.add_parser("analyze-event", help="Проанализировать одно событие.")
    analyze.add_argument("--asset", required=True)
    analyze.add_argument("--event-type", required=True)
    analyze.add_argument("--source-name", required=True)
    analyze.add_argument("--source-url", required=True)
    analyze.add_argument("--official", action="store_true")
    analyze.add_argument("--published-at")
    analyze.add_argument("--price-change-20m-pct", type=float, default=0.0)
    analyze.add_argument("--volume-ratio-vs-7d", type=float, default=1.0)
    analyze.add_argument("--spread-pct", type=float, default=0.0)
    analyze.add_argument("--liquidity-ok", action=argparse.BooleanOptionalAction, default=True)
    analyze.add_argument(
        "--offline-venues",
        help="Биржи через запятую для офлайн-демо. Пример: bybit,binance",
    )
    analyze.add_argument("--send-alert", action="store_true")

    scan = subparsers.add_parser("scan", help="Самостоятельно проверить список монет на Bybit и Binance.")
    scan.add_argument(
        "--assets",
        help="Монеты через запятую. Если не указать, берется SCAN_ASSETS из .env.",
    )
    scan.add_argument(
        "--offline-venues",
        help="Биржи через запятую для офлайн-демо. Пример: bybit,binance",
    )
    scan.add_argument("--send-alert", action="store_true")

    monitor = subparsers.add_parser(
        "monitor-new",
        help="Мониторить новые Spot монеты и отправлять сигналы.",
    )
    monitor.add_argument("--send-alert", action="store_true", help="Отправлять новые сигналы в Telegram.")
    monitor.add_argument("--send-empty", action="store_true", help="Отправлять отчет даже если новых монет нет.")
    monitor.add_argument(
        "--notify-existing",
        action="store_true",
        help="Считать текущие пары новыми. Осторожно: может отправить много сигналов.",
    )
    monitor.add_argument("--loop", action="store_true", help="Запустить постоянный мониторинг.")
    monitor.add_argument(
        "--interval",
        type=int,
        help="Интервал проверки в секундах. Если не указать, берется MONITOR_INTERVAL_SECONDS из .env.",
    )
    monitor.add_argument(
        "--exchanges",
        help="Биржи для мониторинга через запятую. Пример: bybit,binance. Если не указать, берется MONITOR_EXCHANGES из .env.",
    )

    init_db = subparsers.add_parser("init-db", help="Создать базу SQLite.")
    init_db.set_defaults(command="init-db")

    history = subparsers.add_parser("history", help="Показать последние сохраненные сигналы.")
    history.add_argument("--limit", type=int, default=10, help="Сколько сигналов показать, максимум 100.")
    history.add_argument("--asset", help="Фильтр по монете, например BTC.")
    return parser


DEFAULT_HOSTING_ARGS = ["monitor-new", "--loop", "--send-alert"]


def main(argv: list[str] | None = None) -> None:
    cli_args = list(sys.argv[1:] if argv is None else argv)
    if not cli_args:
        cli_args = DEFAULT_HOSTING_ARGS
    parser = build_parser()
    args = parser.parse_args(cli_args)
    settings = Settings.from_env()

    if args.command == "check-symbol":
        checker = VenueChecker.from_settings(settings)
        venues = checker.check_asset(args.asset)
        print(json.dumps([user_venue_dict(venue) for venue in venues], indent=2, ensure_ascii=False))
        return

    if args.command == "init-db":
        SignalPipeline(settings).store.init()
        print(json.dumps({"база": str(settings.database_path), "статус": "готово"}, indent=2, ensure_ascii=False))
        return

    if args.command == "analyze-event":
        checker = VenueChecker.from_settings(settings)
        if args.offline_venues:
            available = tuple(item.strip() for item in args.offline_venues.split(",") if item.strip())
            venues = checker.offline_availability(args.asset, available)
        else:
            venues = checker.check_asset(args.asset)

        event = Event(
            asset=args.asset,
            event_type=args.event_type,
            source=Source(
                name=args.source_name,
                url=args.source_url,
                is_official=bool(args.official),
                published_at=args.published_at,
            ),
        )
        market = MarketMetrics(
            price_change_20m_pct=args.price_change_20m_pct,
            volume_ratio_vs_7d=args.volume_ratio_vs_7d,
            spread_pct=args.spread_pct,
            liquidity_ok=args.liquidity_ok,
        )
        pipeline = SignalPipeline(settings)
        signal = pipeline.analyze(
            event=event,
            market=market,
            venues=venues,
            send_alert=args.send_alert,
        )
        payload = user_signal_dict(signal)
        if args.send_alert:
            payload["telegram"] = telegram_status_text(pipeline.last_alert_status)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if args.command == "monitor-new":
        monitor = NewListingMonitor(settings)
        interval = args.interval or settings.monitor_interval_seconds
        try:
            monitor_exchanges = parse_monitor_exchanges(args.exchanges, settings.monitor_exchanges)
        except ValueError as exc:
            parser.error(str(exc))

        def run_cycle() -> None:
            payload = monitor.run_once(
                send_alert=args.send_alert,
                notify_existing=args.notify_existing,
                send_empty=args.send_empty,
                exchanges=monitor_exchanges,
            )
            print(json.dumps(payload, indent=2, ensure_ascii=False))

        if not args.loop:
            run_cycle()
            return

        started_text = (
            "Crypto Signal Agent запущен\n"
            "Режим: мониторинг новых Spot монет\n"
            f"Биржи: {', '.join(monitor_exchanges)}\n"
            f"Интервал: {interval} секунд\n"
            "Если появится новая USDT-пара, бот отправит сигнал."
        )
        print(started_text, flush=True)
        if args.send_alert:
            TelegramAlerter.from_settings(settings).send_text(started_text)
        try:
            while True:
                run_cycle()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("Мониторинг остановлен.")
            return

    if args.command == "scan":
        assets = parse_assets(args.assets, settings.scan_assets)
        checker = VenueChecker.from_settings(settings)
        results = []
        for asset in assets:
            if args.offline_venues:
                available = tuple(item.strip() for item in args.offline_venues.split(",") if item.strip())
                venues = checker.offline_availability(asset, available)
            else:
                venues = checker.check_asset(asset)
            results.append(evaluate_asset_scan(settings, asset, venues))

        payload = build_scan_payload(tuple(results), settings.require_all_exchanges)
        if args.send_alert:
            sent = TelegramAlerter.from_settings(settings).send_text(format_scan_message(payload))
            payload["telegram"] = "отправлено" if sent else "не отправлено"
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if args.command == "history":
        signals = SignalStore(settings.database_path).recent_signals(limit=args.limit, asset=args.asset)
        payload = {
            "база": str(settings.database_path),
            "фильтр_монета": args.asset.upper() if args.asset else None,
            "показано": len(signals),
            "сигналы": signals,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return


if __name__ == "__main__":
    main()
