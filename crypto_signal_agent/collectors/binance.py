from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_signal_agent.http_client import HttpClientError, JsonHttpClient
from crypto_signal_agent.models import VenueAvailability


@dataclass
class BinanceClient:
    base_url: str
    http: JsonHttpClient

    def spot_symbol(self, asset: str, quote_asset: str) -> str:
        return f"{asset.upper()}{quote_asset.upper()}"

    def check_spot_symbol(self, asset: str, quote_asset: str) -> VenueAvailability:
        symbol = self.spot_symbol(asset, quote_asset)
        try:
            payload = self.http.get_json(
                f"{self.base_url}/api/v3/exchangeInfo",
                params={"symbol": symbol},
            )
        except HttpClientError as exc:
            return VenueAvailability("binance", symbol, False, reason=str(exc))

        symbols: list[dict[str, Any]] = payload.get("symbols", [])
        if not symbols:
            return VenueAvailability("binance", symbol, False, reason="пара не найдена")
        item = symbols[0]
        is_trading = item.get("status") == "TRADING"
        permissions = {str(value).upper() for value in item.get("permissions", [])}
        is_spot = not permissions or "SPOT" in permissions
        if is_trading and is_spot:
            return VenueAvailability("binance", symbol, True, reason="спот-торговля доступна")
        return VenueAvailability(
            "binance",
            symbol,
            False,
            reason=f"статус={item.get('status')} права={sorted(permissions)}",
        )

    def ticker_24h(self, symbol: str) -> dict[str, Any]:
        return self.http.get_json(f"{self.base_url}/api/v3/ticker/24hr", params={"symbol": symbol})
