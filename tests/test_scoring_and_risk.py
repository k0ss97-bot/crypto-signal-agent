from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from crypto_signal_agent.analysis.risk_engine import evaluate_risk
from crypto_signal_agent.analysis.scoring import score_event
from crypto_signal_agent.alerts.telegram import format_signal_message
from crypto_signal_agent.config import Settings
from crypto_signal_agent.listing_monitor import is_active_quote_instrument, parse_bybit_spot_instrument
from crypto_signal_agent.models import Event, MarketMetrics, Source, VenueAvailability
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


if __name__ == "__main__":
    unittest.main()
