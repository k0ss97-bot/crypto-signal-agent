from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    is_official: bool
    published_at: str | None = None


@dataclass(frozen=True)
class Event:
    asset: str
    event_type: str
    source: Source
    detected_at: str = field(default_factory=utc_now_iso)
    notes: tuple[str, ...] = ()

    @property
    def asset_upper(self) -> str:
        return self.asset.upper()


@dataclass(frozen=True)
class VenueAvailability:
    exchange: str
    symbol: str
    available: bool
    market_type: str = "spot"
    reason: str = ""


@dataclass(frozen=True)
class MarketMetrics:
    price_change_20m_pct: float = 0.0
    volume_ratio_vs_7d: float = 1.0
    spread_pct: float = 0.0
    liquidity_ok: bool = True


@dataclass(frozen=True)
class ScoreResult:
    score: int
    label: str
    factors: tuple[str, ...]


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    risk: str
    blocks: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class Signal:
    event: Event
    venues: tuple[VenueAvailability, ...]
    market: MarketMetrics
    score: ScoreResult
    risk: RiskDecision
    signal: str
    bias: str
    confidence: int
    decision: str
    analysis: str
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
