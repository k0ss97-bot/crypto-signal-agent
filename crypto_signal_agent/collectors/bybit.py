from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_signal_agent.http_client import HttpClientError, JsonHttpClient
from crypto_signal_agent.models import VenueAvailability


@dataclass
class BybitClient:
    base_url: str
    http: JsonHttpClient

    def spot_symbol(self, asset: str, quote_asset: str) -> str:
        return f"{asset.upper()}{quote_asset.upper()}"

    def check_spot_symbol(self, asset: str, quote_asset: str) -> VenueAvailability:
        symbol = self.spot_symbol(asset, quote_asset)
        try:
            payload = self.http.get_json(
                f"{self.base_url}/v5/market/instruments-info",
                params={"category": "spot", "symbol": symbol},
            )
        except HttpClientError as exc:
            return VenueAvailability("bybit", symbol, False, reason=str(exc))

        result = payload.get("result") or {}
        instruments = result.get("list") or []
        if not instruments:
            return VenueAvailability("bybit", symbol, False, reason="пара не найдена")
        item = instruments[0]
        status = str(item.get("status", "")).lower()
        if status in {"trading", "1"}:
            return VenueAvailability("bybit", symbol, True, reason="спот-торговля доступна")
        return VenueAvailability("bybit", symbol, False, reason=f"статус={item.get('status')}")

    def list_spot_instruments(self) -> tuple[dict[str, Any], ...]:
        instruments: list[dict[str, Any]] = []
        cursor = ""
        while True:
            params = {"category": "spot", "limit": "1000"}
            if cursor:
                params["cursor"] = cursor
            payload = self.http.get_json(f"{self.base_url}/v5/market/instruments-info", params=params)
            result = payload.get("result") or {}
            instruments.extend(result.get("list") or [])
            cursor = str(result.get("nextPageCursor") or "")
            if not cursor:
                break
        return tuple(instruments)

    def ticker(self, symbol: str) -> dict:
        return self.http.get_json(
            f"{self.base_url}/v5/market/tickers",
            params={"category": "spot", "symbol": symbol},
        )

    def spot_market_metrics(self, symbol: str) -> dict[str, float | bool]:
        payload = self.ticker(symbol)
        result = payload.get("result") or {}
        tickers = result.get("list") or []
        if not tickers:
            return {
                "price_change_20m_pct": 0.0,
                "volume_ratio_vs_7d": 1.0,
                "spread_pct": 0.0,
                "liquidity_ok": False,
            }
        item = tickers[0]
        bid = _to_float(item.get("bid1Price"))
        ask = _to_float(item.get("ask1Price"))
        spread_pct = 0.0
        if bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = ((ask - bid) / mid) * 100 if mid > 0 else 0.0
        return {
            "price_change_20m_pct": 0.0,
            "volume_ratio_vs_7d": 1.0,
            "spread_pct": spread_pct,
            "liquidity_ok": bool(_to_float(item.get("turnover24h")) > 0),
        }


def _to_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
