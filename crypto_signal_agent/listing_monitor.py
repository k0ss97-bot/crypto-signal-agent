from __future__ import annotations

from dataclasses import dataclass

from crypto_signal_agent.collectors.venues import VenueChecker
from crypto_signal_agent.config import Settings
from crypto_signal_agent.models import Event, MarketMetrics, Source
from crypto_signal_agent.pipeline import SignalPipeline
from crypto_signal_agent.presentation import user_signal_dict
from crypto_signal_agent.storage.sqlite_store import SignalStore


@dataclass(frozen=True)
class SpotInstrument:
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
        symbol=symbol,
        base_asset=base_asset,
        quote_asset=quote_asset,
        status=status,
        raw=raw,
    )


def is_active_quote_instrument(instrument: SpotInstrument, quote_asset: str) -> bool:
    return instrument.quote_asset == quote_asset.upper() and instrument.status in {"trading", "1"}


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
    ) -> dict:
        instruments = self._current_bybit_quote_instruments()
        known_before = self.store.known_symbols("bybit")
        is_first_run = not known_before

        if is_first_run and not notify_existing:
            for instrument in instruments:
                self._remember(instrument)
            payload = {
                "режим": "инициализация базы новых монет",
                "биржа": "Bybit",
                "котировка": self.settings.quote_asset,
                "добавлено_в_базу": len(instruments),
                "новых_монет": 0,
                "сообщение": "Первый запуск: текущие пары сохранены как уже известные. Следующие запуски будут ловить только новые монеты.",
            }
            if send_alert and send_empty:
                payload["telegram"] = "отправлено" if self.pipeline.alerter.send_text(format_monitor_message(payload)) else "не отправлено"
            return payload

        new_instruments = [
            instrument
            for instrument in instruments
            if notify_existing or instrument.symbol not in known_before
        ]

        signals = []
        for instrument in new_instruments:
            signal = self._signal_for_new_instrument(instrument, send_alert=send_alert)
            signals.append(user_signal_dict(signal))

        for instrument in instruments:
            self._remember(instrument)

        payload = {
            "режим": "мониторинг новых Bybit Spot монет",
            "биржа": "Bybit",
            "котировка": self.settings.quote_asset,
            "проверено_пар": len(instruments),
            "новых_монет": len(new_instruments),
            "сигналы": signals,
        }
        if send_alert and send_empty and not new_instruments:
            payload["telegram"] = "отправлено" if self.pipeline.alerter.send_text(format_monitor_message(payload)) else "не отправлено"
        elif send_alert:
            payload["telegram"] = "отправлено" if new_instruments else "не отправлялось: новых монет нет"
        return payload

    def _current_bybit_quote_instruments(self) -> tuple[SpotInstrument, ...]:
        parsed = []
        for raw in self.checker.bybit.list_spot_instruments():
            instrument = parse_bybit_spot_instrument(raw)
            if instrument and is_active_quote_instrument(instrument, self.settings.quote_asset):
                parsed.append(instrument)
        return tuple(sorted(parsed, key=lambda item: item.symbol))

    def _signal_for_new_instrument(self, instrument: SpotInstrument, send_alert: bool) -> object:
        venues = self.checker.check_asset(instrument.base_asset)
        metrics = self.checker.bybit.spot_market_metrics(instrument.symbol)
        event = Event(
            asset=instrument.base_asset,
            event_type="bybit_spot_listing",
            source=Source(
                name="Bybit",
                url=f"https://www.bybit.com/trade/spot/{instrument.symbol}",
                is_official=True,
            ),
            notes=("новая спотовая пара обнаружена через Bybit API",),
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
            exchange="bybit",
            symbol=instrument.symbol,
            base_asset=instrument.base_asset,
            quote_asset=instrument.quote_asset,
            status=instrument.status,
            raw=instrument.raw,
        )


def format_monitor_message(payload: dict) -> str:
    if payload.get("режим") == "инициализация базы новых монет":
        return (
            "Мониторинг новых монет Crypto Signal Agent\n"
            f"Режим: {payload['режим']}\n"
            f"Биржа: {payload['биржа']}\n"
            f"Котировка: {payload['котировка']}\n"
            f"Добавлено в базу: {payload['добавлено_в_базу']}\n"
            f"Новых монет: {payload['новых_монет']}\n"
            f"{payload['сообщение']}"
        )
    return (
        "Мониторинг новых монет Crypto Signal Agent\n"
        f"Режим: {payload['режим']}\n"
        f"Биржа: {payload['биржа']}\n"
        f"Котировка: {payload['котировка']}\n"
        f"Проверено пар: {payload['проверено_пар']}\n"
        f"Новых монет: {payload['новых_монет']}"
    )
