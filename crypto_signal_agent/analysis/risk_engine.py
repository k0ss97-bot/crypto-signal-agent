from __future__ import annotations

from crypto_signal_agent.config import Settings
from crypto_signal_agent.models import Event, MarketMetrics, RiskDecision, VenueAvailability
from crypto_signal_agent.presentation import exchange_label


def evaluate_risk(
    settings: Settings,
    event: Event,
    market: MarketMetrics,
    venues: tuple[VenueAvailability, ...],
) -> RiskDecision:
    blocks: list[str] = []
    warnings: list[str] = []

    if settings.no_signal_if_source_unverified and not event.source.is_official:
        blocks.append("источник не подтвержден")

    primary = next((venue for venue in venues if venue.exchange == settings.primary_exchange), None)
    if primary is None:
        blocks.append(f"основная биржа не проверена: {exchange_label(settings.primary_exchange)}")
    elif not primary.available:
        blocks.append(
            f"спот-пара недоступна на основной бирже: {exchange_label(primary.exchange)} {primary.symbol}"
        )

    missing = [venue for venue in venues if not venue.available]
    missing_confirmation = [venue for venue in missing if venue.exchange != settings.primary_exchange]
    if settings.require_all_exchanges and missing_confirmation:
        names = ", ".join(f"{exchange_label(venue.exchange)} {venue.symbol}" for venue in missing_confirmation)
        blocks.append(f"нет обязательной биржи: {names}")
    elif missing_confirmation:
        names = ", ".join(f"{exchange_label(venue.exchange)} {venue.symbol}" for venue in missing_confirmation)
        warnings.append(f"нет подтверждения на бирже: {names}")

    if market.spread_pct > settings.max_spread_pct:
        blocks.append(f"спред слишком высокий: {market.spread_pct:.4g}% > {settings.max_spread_pct:.4g}%")

    if market.volume_ratio_vs_7d < settings.min_volume_ratio_vs_7d:
        warnings.append(
            f"объем ниже порога: {market.volume_ratio_vs_7d:.4g}x < {settings.min_volume_ratio_vs_7d:.4g}x"
        )

    if settings.min_liquidity_ok and not market.liquidity_ok:
        blocks.append("ликвидность недостаточная")

    if settings.live_trading_enabled:
        blocks.append("LIVE_TRADING_ENABLED включен, но в MVP исполнение сделок отключено")

    risk = "low"
    if market.price_change_20m_pct >= 40 or market.spread_pct > settings.max_spread_pct * 0.7:
        risk = "high"
    elif market.price_change_20m_pct >= 15 or market.volume_ratio_vs_7d >= 3:
        risk = "medium"
    if blocks:
        risk = "blocked"

    return RiskDecision(
        allowed=not blocks,
        risk=risk,
        blocks=tuple(blocks),
        warnings=tuple(warnings),
    )
