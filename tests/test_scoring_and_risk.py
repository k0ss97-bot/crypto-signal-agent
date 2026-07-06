from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from crypto_signal_agent.analysis.risk_engine import evaluate_risk
from crypto_signal_agent.analysis.scoring import score_event
from crypto_signal_agent.alerts.telegram import format_signal_message
from crypto_signal_agent.config import Settings
from crypto_signal_agent.listing_monitor import (
    NewListingMonitor,
    is_active_quote_instrument,
    parse_binance_spot_instrument,
    parse_bybit_spot_instrument,
    parse_monitor_exchanges,
)
from crypto_signal_agent.models import Event, MarketMetrics, RiskDecision, ScoreResult, Signal, Source, VenueAvailability
from crypto_signal_agent.pipeline import SignalPipeline
from crypto_signal_agent.presentation import user_signal_dict
from crypto_signal_agent.scanner import build_scan_payload, evaluate_asset_scan, format_scan_message


def make_settings(**overrides: object) -> Settings:
    values = {
        "openai_api_key": None,
        "openai_model": "gpt-5.5",
        "quote_asset": "USDT",
        "primary_exchange": "bybit",
        "required_exchanges": ("bybit", "binance"),
        "require_all_exchanges": True,
        "scan_assets": ("BTC", "ETH", "SOL"),
        "binance_base_url": "https://api.binance.com",
        "bybit_base_url": "https://api.bybit.com",
        "database_path": Path(tempfile.mkdtemp()) / "signals.sqlite3",
        "telegram_bot_token": None,
        "telegram_chat_id": None,
        "max_spread_pct": 0.35,
        "min_volume_ratio_vs_7d": 1.0,
        "min_liquidity_ok": True,
        "no_signal_if_source_unverified": True,
        "live_trading_enabled": False,
        "monitor_interval_seconds": 300,
        "monitor_exchanges": ("bybit",),
    }
    values.update(overrides)
    return Settings(**values)


def make_event(official: bool = True) -> Event:
    return Event(
        asset="ABC",
        event_type="major_cex_spot_listing",
        source=Source(name="Bybit", url="https://example.com", is_official=official),
    )


def make_negative_event() -> Event:
    return Event(
        asset="ABC",
        event_type="hack",
        source=Source(name="Project blog", url="https://example.com", is_official=True),
    )


def make_venues(binance: bool = True, bybit: bool = True) -> tuple[VenueAvailability, ...]:
    return (
        VenueAvailability("binance", "ABCUSDT", binance),
        VenueAvailability("bybit", "ABCUSDT", bybit),
    )


class ScoringAndRiskTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("OPENAI_API_KEY", None)

    def test_missing_binance_blocks_when_all_exchanges_required(self) -> None:
        settings = make_settings(require_all_exchanges=True)
        risk = evaluate_risk(
            settings,
            make_event(),
            MarketMetrics(price_change_20m_pct=10, volume_ratio_vs_7d=4, spread_pct=0.1),
            make_venues(binance=False, bybit=True),
        )

        self.assertFalse(risk.allowed)
        self.assertTrue(any("нет обязательной биржи" in block for block in risk.blocks))

    def test_bybit_is_always_required_for_user_tradeability(self) -> None:
        settings = make_settings(require_all_exchanges=False)
        risk = evaluate_risk(
            settings,
            make_event(),
            MarketMetrics(price_change_20m_pct=10, volume_ratio_vs_7d=4, spread_pct=0.1),
            make_venues(binance=True, bybit=False),
        )

        self.assertFalse(risk.allowed)
        self.assertTrue(any("спот-пара недоступна на основной бирже" in block for block in risk.blocks))

    def test_bybit_primary_mode_allows_missing_binance_warning(self) -> None:
        settings = make_settings(require_all_exchanges=False)
        risk = evaluate_risk(
            settings,
            make_event(),
            MarketMetrics(price_change_20m_pct=10, volume_ratio_vs_7d=4, spread_pct=0.1),
            make_venues(binance=False, bybit=True),
        )

        self.assertTrue(risk.allowed)
        self.assertTrue(any("нет подтверждения на бирже" in warning for warning in risk.warnings))

    def test_unofficial_source_blocks_signal(self) -> None:
        settings = make_settings()
        risk = evaluate_risk(
            settings,
            make_event(official=False),
            MarketMetrics(price_change_20m_pct=10, volume_ratio_vs_7d=4, spread_pct=0.1),
            make_venues(),
        )

        self.assertFalse(risk.allowed)
        self.assertIn("источник не подтвержден", risk.blocks)

    def test_official_listing_with_volume_scores_watch(self) -> None:
        score = score_event(
            make_event(),
            MarketMetrics(price_change_20m_pct=18, volume_ratio_vs_7d=6.2, spread_pct=0.1),
            make_venues(),
        )

        self.assertGreaterEqual(score.score, 80)
        self.assertEqual(score.label, "strong_watch")

    def test_pipeline_saves_signal_and_blocks_missing_bybit(self) -> None:
        settings = make_settings()
        signal = SignalPipeline(settings).analyze(
            event=make_event(),
            market=MarketMetrics(price_change_20m_pct=18, volume_ratio_vs_7d=6.2, spread_pct=0.1),
            venues=make_venues(binance=True, bybit=False),
        )

        self.assertEqual(signal.signal, "avoid")
        self.assertEqual(signal.bias, "no_trade")
        self.assertEqual(signal.risk.risk, "blocked")
        self.assertTrue(settings.database_path.exists())

    def test_history_returns_recent_signals_and_filters_by_asset(self) -> None:
        settings = make_settings()
        pipeline = SignalPipeline(settings)
        pipeline.analyze(
            event=make_event(),
            market=MarketMetrics(price_change_20m_pct=18, volume_ratio_vs_7d=6.2, spread_pct=0.1),
            venues=make_venues(),
        )
        pipeline.analyze(
            event=Event(
                asset="XYZ",
                event_type="major_cex_spot_listing",
                source=Source(name="Bybit", url="https://example.com/xyz", is_official=True),
            ),
            market=MarketMetrics(price_change_20m_pct=9, volume_ratio_vs_7d=3.1, spread_pct=0.1),
            venues=(
                VenueAvailability("binance", "XYZUSDT", True),
                VenueAvailability("bybit", "XYZUSDT", True),
            ),
        )

        recent = pipeline.store.recent_signals(limit=1)
        filtered = pipeline.store.recent_signals(limit=10, asset="ABC")

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["монета"], "XYZ")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["монета"], "ABC")
        self.assertIn("id_сигнала", filtered[0])

    def test_telegram_alert_is_sent_once_for_same_event(self) -> None:
        class FakeAlerter:
            def __init__(self) -> None:
                self.calls = 0

            def enabled(self) -> bool:
                return True

            def send_signal(self, signal: Signal) -> bool:
                self.calls += 1
                return True

        settings = make_settings()
        pipeline = SignalPipeline(settings)
        fake_alerter = FakeAlerter()
        pipeline.alerter = fake_alerter
        first_event = Event(
            asset="ABC",
            event_type="major_cex_spot_listing",
            source=Source(name="Bybit", url="https://example.com/abc", is_official=True),
            detected_at="2026-07-06T00:00:00Z",
        )
        second_event = Event(
            asset="ABC",
            event_type="major_cex_spot_listing",
            source=Source(name="Bybit", url="https://example.com/abc", is_official=True),
            detected_at="2026-07-06T00:05:00Z",
        )

        pipeline.analyze(
            event=first_event,
            market=MarketMetrics(price_change_20m_pct=18, volume_ratio_vs_7d=6.2, spread_pct=0.1),
            venues=make_venues(),
            send_alert=True,
        )
        self.assertEqual(pipeline.last_alert_status, "sent")
        pipeline.analyze(
            event=second_event,
            market=MarketMetrics(price_change_20m_pct=19, volume_ratio_vs_7d=6.5, spread_pct=0.1),
            venues=make_venues(),
            send_alert=True,
        )

        self.assertEqual(fake_alerter.calls, 1)
        self.assertEqual(pipeline.last_alert_status, "duplicate_skipped")

    def test_negative_event_becomes_sell_risk_when_tradeable(self) -> None:
        settings = make_settings()
        signal = SignalPipeline(settings).analyze(
            event=make_negative_event(),
            market=MarketMetrics(price_change_20m_pct=-12, volume_ratio_vs_7d=4, spread_pct=0.1),
            venues=make_venues(binance=True, bybit=True),
        )

        self.assertEqual(signal.signal, "sell_risk")
        self.assertEqual(signal.bias, "sell_bias")

    def test_user_facing_outputs_are_russian(self) -> None:
        settings = make_settings()
        signal = SignalPipeline(settings).analyze(
            event=make_event(),
            market=MarketMetrics(price_change_20m_pct=18, volume_ratio_vs_7d=6.2, spread_pct=0.1),
            venues=make_venues(binance=True, bybit=True),
        )

        message = format_signal_message(signal)
        payload = user_signal_dict(signal)

        self.assertIn("Событие:", message)
        self.assertIn("Сигнал:", message)
        self.assertIn("Биржи:", message)
        self.assertIn("монета", payload)
        self.assertEqual(payload["сигнал"], "наблюдать")

    def test_scan_blocks_missing_binance_in_strict_mode(self) -> None:
        settings = make_settings(require_all_exchanges=True)
        result = evaluate_asset_scan(settings, "ABC", make_venues(binance=False, bybit=True))

        self.assertEqual(result.status, "заблокировано")
        self.assertTrue(any("нет обязательной биржи" in block for block in result.blocks))

    def test_scan_allows_missing_binance_in_soft_mode(self) -> None:
        settings = make_settings(require_all_exchanges=False)
        result = evaluate_asset_scan(settings, "ABC", make_venues(binance=False, bybit=True))

        self.assertEqual(result.status, "доступно с предупреждением")
        self.assertTrue(any("нет подтверждения на бирже" in warning for warning in result.warnings))

    def test_scan_message_is_russian(self) -> None:
        settings = make_settings()
        result = evaluate_asset_scan(settings, "ABC", make_venues(binance=True, bybit=True))
        payload = build_scan_payload((result,), strict=True)
        message = format_scan_message(payload)

        self.assertIn("Проверка монет", message)
        self.assertIn("Время проверки:", message)
        self.assertIn("ABC: доступно", message)
        self.assertIn("Bybit ABCUSDT: да", message)

    def test_parse_bybit_spot_instrument(self) -> None:
        instrument = parse_bybit_spot_instrument(
            {
                "symbol": "ABCUSDT",
                "baseCoin": "ABC",
                "quoteCoin": "USDT",
                "status": "Trading",
            }
        )

        self.assertIsNotNone(instrument)
        assert instrument is not None
        self.assertTrue(is_active_quote_instrument(instrument, "USDT"))
        self.assertEqual(instrument.base_asset, "ABC")

    def test_parse_bybit_spot_instrument_rejects_missing_fields(self) -> None:
        self.assertIsNone(parse_bybit_spot_instrument({"symbol": "ABCUSDT"}))

    def test_parse_binance_spot_instrument(self) -> None:
        instrument = parse_binance_spot_instrument(
            {
                "symbol": "XYZUSDT",
                "baseAsset": "XYZ",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "permissions": ["SPOT"],
                "isSpotTradingAllowed": True,
            }
        )

        self.assertIsNotNone(instrument)
        assert instrument is not None
        self.assertTrue(is_active_quote_instrument(instrument, "USDT"))
        self.assertEqual(instrument.exchange, "binance")
        self.assertEqual(instrument.base_asset, "XYZ")

    def test_parse_binance_spot_instrument_rejects_non_spot(self) -> None:
        self.assertIsNone(
            parse_binance_spot_instrument(
                {
                    "symbol": "XYZUSDT",
                    "baseAsset": "XYZ",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "permissions": ["MARGIN"],
                    "isSpotTradingAllowed": False,
                }
            )
        )

    def test_parse_monitor_exchanges_deduplicates_and_validates(self) -> None:
        self.assertEqual(parse_monitor_exchanges("bybit,binance,bybit", ("bybit",)), ("bybit", "binance"))
        with self.assertRaises(ValueError):
            parse_monitor_exchanges("coinbase", ("bybit",))

    def test_monitor_can_process_bybit_and_binance_new_listings(self) -> None:
        class FakeBybit:
            def list_spot_instruments(self) -> tuple[dict, ...]:
                return (
                    {
                        "symbol": "ABCUSDT",
                        "baseCoin": "ABC",
                        "quoteCoin": "USDT",
                        "status": "Trading",
                    },
                )

        class FakeBinance:
            def list_spot_symbols(self) -> tuple[dict, ...]:
                return (
                    {
                        "symbol": "XYZUSDT",
                        "baseAsset": "XYZ",
                        "quoteAsset": "USDT",
                        "status": "TRADING",
                        "permissions": ["SPOT"],
                        "isSpotTradingAllowed": True,
                    },
                )

        class FakeChecker:
            bybit = FakeBybit()
            binance = FakeBinance()

            def check_asset(self, asset: str) -> tuple[VenueAvailability, ...]:
                return (
                    VenueAvailability("bybit", f"{asset}USDT", True),
                    VenueAvailability("binance", f"{asset}USDT", True),
                )

            def market_metrics(self, exchange: str, symbol: str) -> dict[str, float | bool]:
                return {
                    "price_change_20m_pct": 0.0,
                    "volume_ratio_vs_7d": 1.0,
                    "spread_pct": 0.1,
                    "liquidity_ok": True,
                }

        class FakeAlerter:
            def send_text(self, text: str) -> bool:
                return True

        class FakePipeline:
            def __init__(self) -> None:
                self.events: list[Event] = []
                self.last_alert_status: str | None = None
                self.alerter = FakeAlerter()

            def analyze(
                self,
                event: Event,
                market: MarketMetrics,
                venues: tuple[VenueAvailability, ...],
                send_alert: bool = False,
            ) -> Signal:
                self.events.append(event)
                self.last_alert_status = "sent" if send_alert else None
                return Signal(
                    event=event,
                    venues=venues,
                    market=market,
                    score=ScoreResult(80, "strong_watch", ()),
                    risk=RiskDecision(True, "low", (), ()),
                    signal="watch",
                    bias="long_bias",
                    confidence=80,
                    decision="watch_not_chase",
                    analysis="ok",
                )

        settings = make_settings(monitor_exchanges=("bybit", "binance"))
        monitor = NewListingMonitor(settings)
        monitor.checker = FakeChecker()
        fake_pipeline = FakePipeline()
        monitor.pipeline = fake_pipeline

        payload = monitor.run_once(send_alert=True, notify_existing=True, exchanges=("bybit", "binance"))

        self.assertEqual(payload["новых_монет"], 2)
        self.assertEqual(payload["telegram"], "отправлено: 2")
        self.assertEqual(
            {event.event_type for event in fake_pipeline.events},
            {"bybit_spot_listing", "binance_spot_listing"},
        )
        self.assertIn("ABCUSDT", monitor.store.known_symbols("bybit"))
        self.assertIn("XYZUSDT", monitor.store.known_symbols("binance"))


if __name__ == "__main__":
    unittest.main()
