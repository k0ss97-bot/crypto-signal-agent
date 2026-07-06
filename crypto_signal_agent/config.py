from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_model: str
    quote_asset: str
    primary_exchange: str
    required_exchanges: tuple[str, ...]
    require_all_exchanges: bool
    scan_assets: tuple[str, ...]
    binance_base_url: str
    bybit_base_url: str
    database_path: Path
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    max_spread_pct: float
    min_volume_ratio_vs_7d: float
    min_liquidity_ok: bool
    no_signal_if_source_unverified: bool
    live_trading_enabled: bool
    monitor_interval_seconds: int
    monitor_exchanges: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
            quote_asset=os.getenv("QUOTE_ASSET", "USDT").upper(),
            primary_exchange=os.getenv("PRIMARY_EXCHANGE", "bybit").strip().lower(),
            required_exchanges=env_list("REQUIRED_EXCHANGES", ("bybit", "binance")),
            require_all_exchanges=env_bool("REQUIRE_ALL_EXCHANGES", True),
            scan_assets=tuple(asset.upper() for asset in env_list("SCAN_ASSETS", ("BTC", "ETH", "SOL", "BNB", "XRP"))),
            binance_base_url=os.getenv("BINANCE_BASE_URL", "https://api.binance.com").rstrip("/"),
            bybit_base_url=os.getenv("BYBIT_BASE_URL", "https://api.bybit.com").rstrip("/"),
            database_path=Path(os.getenv("DATABASE_PATH", "data/signals.sqlite3")),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
            max_spread_pct=env_float("MAX_SPREAD_PCT", 0.35),
            min_volume_ratio_vs_7d=env_float("MIN_VOLUME_RATIO_VS_7D", 1.0),
            min_liquidity_ok=env_bool("MIN_LIQUIDITY_OK", True),
            no_signal_if_source_unverified=env_bool("NO_SIGNAL_IF_SOURCE_UNVERIFIED", True),
            live_trading_enabled=env_bool("LIVE_TRADING_ENABLED", False),
            monitor_interval_seconds=env_int("MONITOR_INTERVAL_SECONDS", 300),
            monitor_exchanges=env_list("MONITOR_EXCHANGES", ("bybit",)),
        )
