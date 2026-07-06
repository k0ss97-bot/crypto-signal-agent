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

        symbols: list[dict[str, Any]] = payload.get("symbols") or []
        if not symbols:
            return VenueAvailability("binance", symbol, False, reason="пара не найдена")
        item = symbols[0]
        is_trading = item.get("status") == "TRADING"
        permissions = {str(value).upper() for value in item.get("permissions") or []}
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

    def list_spot_symbols(self) -> tuple[dict[str, Any], ...]:
        payload = self.http.get_json(f"{self.base_url}/api/v3/exchangeInfo")
        return tuple(payload.get("symbols") or [])

    def spot_market_metrics(self, symbol: str) -> dict[str, float | bool]:
        try:
            item = self.ticker_24h(symbol)
        except HttpClientError:
            return {
                "price_change_20m_pct": 0.0,
                "volume_ratio_vs_7d": 1.0,
                "spread_pct": 0.0,
                "liquidity_ok": False,
            }

        bid = _to_float(item.get("bidPrice"))
        ask = _to_float(item.get("askPrice"))
        spread_pct = 0.0
        if bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = ((ask - bid) / mid) * 100 if mid > 0 else 0.0
        return {
            "price_change_20m_pct": 0.0,
            "volume_ratio_vs_7d": 1.0,
            "spread_pct": spread_pct,
            "liquidity_ok": bool(_to_float(item.get("quoteVolume")) > 0),
        }


def _to_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
