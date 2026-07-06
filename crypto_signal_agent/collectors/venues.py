from __future__ import annotations

from dataclasses import dataclass

from crypto_signal_agent.collectors.binance import BinanceClient
from crypto_signal_agent.collectors.bybit import BybitClient
from crypto_signal_agent.config import Settings
from crypto_signal_agent.http_client import JsonHttpClient
from crypto_signal_agent.models import VenueAvailability


@dataclass
class VenueChecker:
    settings: Settings
    binance: BinanceClient
    bybit: BybitClient

    @classmethod
    def from_settings(cls, settings: Settings) -> "VenueChecker":
        http = JsonHttpClient()
        return cls(
            settings=settings,
            binance=BinanceClient(settings.binance_base_url, http),
            bybit=BybitClient(settings.bybit_base_url, http),
        )

    def check_asset(self, asset: str) -> tuple[VenueAvailability, ...]:
        checks: list[VenueAvailability] = []
        for exchange in self.settings.required_exchanges:
            if exchange == "binance":
                checks.append(self.binance.check_spot_symbol(asset, self.settings.quote_asset))
            elif exchange == "bybit":
                checks.append(self.bybit.check_spot_symbol(asset, self.settings.quote_asset))
            else:
                checks.append(
                    VenueAvailability(
                        exchange=exchange,
                        symbol=f"{asset.upper()}{self.settings.quote_asset}",
                        available=False,
                        reason="биржа не поддерживается",
                    )
                )
        return tuple(checks)

    def offline_availability(self, asset: str, available_exchanges: tuple[str, ...]) -> tuple[VenueAvailability, ...]:
        available = {item.lower() for item in available_exchanges}
        return tuple(
            VenueAvailability(
                exchange=exchange,
                symbol=f"{asset.upper()}{self.settings.quote_asset}",
                available=exchange in available,
                reason="доступно в офлайн-проверке" if exchange in available else "не указано в офлайн-проверке",
            )
            for exchange in self.settings.required_exchanges
        )

    def market_metrics(self, exchange: str, symbol: str) -> dict[str, float | bool]:
        if exchange == "bybit":
            return self.bybit.spot_market_metrics(symbol)
        if exchange == "binance":
            return self.binance.spot_market_metrics(symbol)
        return {
            "price_change_20m_pct": 0.0,
            "volume_ratio_vs_7d": 1.0,
            "spread_pct": 0.0,
            "liquidity_ok": False,
        }
