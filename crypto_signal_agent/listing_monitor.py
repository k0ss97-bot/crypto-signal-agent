from __future__ import annotations

from dataclasses import dataclass

from crypto_signal_agent.collectors.venues import VenueChecker
from crypto_signal_agent.config import Settings
from crypto_signal_agent.models import Event, MarketMetrics, Source
from crypto_signal_agent.pipeline import SignalPipeline
from crypto_signal_agent.presentation import exchange_label, user_signal_dict
from crypto_signal_agent.storage.sqlite_store import SignalStore


@dataclass(frozen=True)
class SpotInstrument:
    exchange: str
    symbol: str
    base_asset: str
    quote_asset: str
    status: str
    raw: dict


def parse_bybit_spot_instrument(raw: dict) -> SpotInstrument | None:
    symbol = str(raw.get("symbol") or "").upper()
    base_asset = str(raw.get("baseCoin") or "").upper()
    quote_asset = str(raw.get("quoteCoin") or "").upper()
    status = str(raw.get("status") or "").lower()
    if not symbol or not base_asset or not quote_asset:
        return None
    return SpotInstrument(
        exchange="bybit",
        symbol=symbol,
        base_asset=base_asset,
        quote_asset=quote_asset,
        status=status,
        raw=raw,
    )


def parse_binance_spot_instrument(raw: dict) -> SpotInstrument | None:
    symbol = str(raw.get("symbol") or "").upper()
    base_asset = str(raw.get("baseAsset") or "").upper()
    quote_asset = str(raw.get("quoteAsset") or "").upper()
    status = str(raw.get("status") or "").lower()
    permissions = {str(value).upper() for value in raw.get("permissions") or []}
    is_spot_allowed = bool(raw.get("isSpotTradingAllowed", True))
    if permissions and "SPOT" not in permissions:
        is_spot_allowed = False
    if not symbol or not base_asset or not quote_asset or not is_spot_allowed:
        return None
    return SpotInstrument(
        exchange="binance",
        symbol=symbol,
        base_asset=base_asset,
        quote_asset=quote_asset,
        status=status,
        raw=raw,
    )


def is_active_quote_instrument(instrument: SpotInstrument, quote_asset: str) -> bool:
    return instrument.quote_asset == quote_asset.upper() and instrument.status in {"trading", "1"}


def parse_monitor_exchanges(value: str | tuple[str, ...] | list[str] | None, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_items: tuple[str, ...]
    if value is None:
        raw_items = default
    elif isinstance(value, str):
        raw_items = tuple(value.split(","))
    else:
        raw_items = tuple(value)

    supported = {"bybit", "binance"}
    exchanges: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        exchange = raw_item.strip().lower()
        if not exchange or exchange in seen:
            continue
        if exchange not in supported:
            raise ValueError(f"мониторинг биржи не поддерживается: {exchange}")
        seen.add(exchange)
        exchanges.append(exchange)
    if not exchanges:
        raise ValueError("нужно указать хотя бы одну биржу для мониторинга")
    return tuple(exchanges)


class NewListingMonitor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SignalStore(settings.database_path)
        self.checker = VenueChecker.from_settings(settings)
        self.pipeline = SignalPipeline(settings)

    def run_once(
        self,
        send_alert: bool = False,
        notify_existing: bool = False,
        send_empty: bool = False,
        exchanges: tuple[str, ...] | None = None,
    ) -> dict:
        monitor_exchanges = parse_monitor_exchanges(exchanges, self.settings.monitor_exchanges)
        instruments_by_exchange = {
            exchange: self._current_quote_instruments(exchange) for exchange in monitor_exchanges
        }
        known_before_by_exchange = {
            exchange: self.store.known_symbols(exchange) for exchange in monitor_exchanges
        }
        instruments = tuple(
            instrument
            for exchange in monitor_exchanges
            for instrument in instruments_by_exchange[exchange]
        )
        is_first_run = any(not known_before_by_exchange[exchange] for exchange in monitor_exchanges)

        if is_first_run and not notify_existing:
            for instrument in instruments:
                self._remember(instrument)
            payload = {
                "режим": "инициализация базы новых монет",
                "биржи": [exchange_label(exchange) for exchange in monitor_exchanges],
                "котировка": self.settings.quote_asset,
                "добавлено_в_базу": len(instruments),
                "новых_монет": 0,
                "по_биржам": [
                    {
                        "биржа": exchange_label(exchange),
                        "добавлено_в_базу": len(instruments_by_exchange[exchange]),
                    }
                    for exchange in monitor_exchanges
                ],
                "сообщение": "Первый запуск: текущие пары сохранены как уже известные. Следующие запуски будут ловить только новые монеты.",
            }
            if send_alert and send_empty:
                payload["telegram"] = "отправлено" if self.pipeline.alerter.send_text(format_monitor_message(payload)) else "не отправлено"
            return payload

        new_instruments = [
            instrument
            for instrument in instruments
            if notify_existing or instrument.symbol not in known_before_by_exchange[instrument.exchange]
        ]

        signals = []
        alert_statuses: list[str] = []
        for instrument in new_instruments:
            signal = self._signal_for_new_instrument(instrument, send_alert=send_alert)
            payload = user_signal_dict(signal)
            if send_alert:
                status = self.pipeline.last_alert_status or "not_requested"
                alert_statuses.append(status)
                payload["telegram"] = telegram_status_text(status)
            signals.append(payload)

        for instrument in instruments:
            self._remember(instrument)

        payload = {
            "режим": "мониторинг новых Spot монет",
            "биржи": [exchange_label(exchange) for exchange in monitor_exchanges],
            "котировка": self.settings.quote_asset,
            "проверено_пар": len(instruments),
            "новых_монет": len(new_instruments),
            "по_биржам": [
                {
                    "биржа": exchange_label(exchange),
                    "проверено_пар": len(instruments_by_exchange[exchange]),
                    "новых_монет": sum(1 for instrument in new_instruments if instrument.exchange == exchange),
                }
                for exchange in monitor_exchanges
            ],
            "сигналы": signals,
        }
        if send_alert and send_empty and not new_instruments:
            payload["telegram"] = "отправлено" if self.pipeline.alerter.send_text(format_monitor_message(payload)) else "не отправлено"
        elif send_alert:
            payload["telegram"] = monitor_telegram_summary(alert_statuses) if new_instruments else "не отправлялось: новых монет нет"
        return payload

    def _current_quote_instruments(self, exchange: str) -> tuple[SpotInstrument, ...]:
        if exchange == "bybit":
            return self._current_bybit_quote_instruments()
        if exchange == "binance":
            return self._current_binance_quote_instruments()
        raise ValueError(f"мониторинг биржи не поддерживается: {exchange}")

    def _current_bybit_quote_instruments(self) -> tuple[SpotInstrument, ...]:
        parsed = []
        for raw in self.checker.bybit.list_spot_instruments():
            instrument = parse_bybit_spot_instrument(raw)
            if instrument and is_active_quote_instrument(instrument, self.settings.quote_asset):
                parsed.append(instrument)
        return tuple(sorted(parsed, key=lambda item: item.symbol))

    def _current_binance_quote_instruments(self) -> tuple[SpotInstrument, ...]:
        parsed = []
        for raw in self.checker.binance.list_spot_symbols():
            instrument = parse_binance_spot_instrument(raw)
            if instrument and is_active_quote_instrument(instrument, self.settings.quote_asset):
                parsed.append(instrument)
        return tuple(sorted(parsed, key=lambda item: item.symbol))

    def _signal_for_new_instrument(self, instrument: SpotInstrument, send_alert: bool) -> object:
        venues = self.checker.check_asset(instrument.base_asset)
        metrics = self.checker.market_metrics(instrument.exchange, instrument.symbol)
        event = Event(
            asset=instrument.base_asset,
            event_type=f"{instrument.exchange}_spot_listing",
            source=Source(
                name=exchange_label(instrument.exchange),
                url=trade_url(instrument),
                is_official=True,
            ),
            notes=(f"новая спотовая пара обнаружена через {exchange_label(instrument.exchange)} API",),
        )
        return self.pipeline.analyze(
            event=event,
            market=MarketMetrics(
                price_change_20m_pct=float(metrics["price_change_20m_pct"]),
                volume_ratio_vs_7d=float(metrics["volume_ratio_vs_7d"]),
                spread_pct=float(metrics["spread_pct"]),
                liquidity_ok=bool(metrics["liquidity_ok"]),
            ),
            venues=venues,
            send_alert=send_alert,
        )

    def _remember(self, instrument: SpotInstrument) -> None:
        self.store.upsert_listing(
            exchange=instrument.exchange,
            symbol=instrument.symbol,
            base_asset=instrument.base_asset,
            quote_asset=instrument.quote_asset,
            status=instrument.status,
            raw=instrument.raw,
        )


def format_monitor_message(payload: dict) -> str:
    if payload.get("режим") == "инициализация базы новых монет":
        exchange_text = ", ".join(payload.get("биржи", [])) or str(payload.get("биржа", ""))
        return (
            "Мониторинг новых монет Crypto Signal Agent\n"
            f"Режим: {payload['режим']}\n"
            f"Биржи: {exchange_text}\n"
            f"Котировка: {payload['котировка']}\n"
            f"Добавлено в базу: {payload['добавлено_в_базу']}\n"
            f"Новых монет: {payload['новых_монет']}\n"
            f"{payload['сообщение']}"
        )
    exchange_text = ", ".join(payload.get("биржи", [])) or str(payload.get("биржа", ""))
    return (
        "Мониторинг новых монет Crypto Signal Agent\n"
        f"Режим: {payload['режим']}\n"
        f"Биржи: {exchange_text}\n"
        f"Котировка: {payload['котировка']}\n"
        f"Проверено пар: {payload['проверено_пар']}\n"
        f"Новых монет: {payload['новых_монет']}"
    )


def trade_url(instrument: SpotInstrument) -> str:
    if instrument.exchange == "binance":
        return f"https://www.binance.com/en/trade/{instrument.base_asset}_{instrument.quote_asset}?type=spot"
    return f"https://www.bybit.com/trade/spot/{instrument.symbol}"


def telegram_status_text(status: str | None) -> str:
    if status == "sent":
        return "отправлено"
    if status == "duplicate_skipped":
        return "не отправлено: дубль"
    if status == "disabled":
        return "не отправлено: Telegram не настроен"
    if status == "failed":
        return "не отправлено: ошибка Telegram"
    return "не отправлялось"


def monitor_telegram_summary(statuses: list[str]) -> str:
    if not statuses:
        return "не отправлялось: новых монет нет"
    sent = statuses.count("sent")
    duplicates = statuses.count("duplicate_skipped")
    disabled = statuses.count("disabled")
    failed = statuses.count("failed")
    parts = []
    if sent:
        parts.append(f"отправлено: {sent}")
    if duplicates:
        parts.append(f"дублей пропущено: {duplicates}")
    if disabled:
        parts.append(f"Telegram не настроен: {disabled}")
    if failed:
        parts.append(f"ошибок: {failed}")
    return ", ".join(parts) if parts else "не отправлено"
