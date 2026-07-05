from __future__ import annotations

from crypto_signal_agent.models import Event, MarketMetrics, ScoreResult, VenueAvailability


MAJOR_SPOT_LISTINGS = {
    "major_cex_spot_listing",
    "binance_spot_listing",
    "bybit_spot_listing",
    "coinbase_spot_listing",
    "upbit_spot_listing",
}

FUTURES_LISTINGS = {
    "binance_futures_listing",
    "bybit_futures_listing",
    "major_cex_futures_listing",
}

NEGATIVE_EVENTS = {
    "delisting",
    "monitoring_tag",
    "hack",
    "exploit",
    "security_incident",
    "legal_negative",
}


def score_event(
    event: Event,
    market: MarketMetrics,
    venues: tuple[VenueAvailability, ...],
) -> ScoreResult:
    score = 50
    factors: list[str] = ["базовая оценка 50"]
    event_type = event.event_type.lower()

    if event.source.is_official:
        score += 25
        factors.append("+25 официальный источник")
    else:
        score -= 25
        factors.append("-25 источник не подтвержден")

    if event_type in MAJOR_SPOT_LISTINGS:
        score += 25
        factors.append("+25 спотовый листинг на крупной бирже")
    elif event_type in FUTURES_LISTINGS:
        score += 10
        factors.append("+10 фьючерсный листинг")
    elif event_type in NEGATIVE_EVENTS:
        score -= 40
        factors.append("-40 негативное событие")

    if market.price_change_20m_pct >= 80:
        score -= 25
        factors.append("-25 цена уже выросла на 80% или больше")
    elif market.price_change_20m_pct >= 40:
        score -= 20
        factors.append("-20 цена уже выросла на 40% или больше")

    if market.volume_ratio_vs_7d >= 3:
        score += 15
        factors.append("+15 объем выше среднего более чем в 3 раза")

    if market.liquidity_ok:
        score += 10
        factors.append("+10 ликвидность достаточная")
    else:
        score -= 20
        factors.append("-20 ликвидность слабая")

    if all(venue.available for venue in venues):
        score += 10
        factors.append("+10 обязательные биржи доступны")
    else:
        score -= 30
        factors.append("-30 нет одной из обязательных бирж")

    score = max(0, min(100, score))
    return ScoreResult(score=score, label=score_label(score), factors=tuple(factors))


def score_label(score: int) -> str:
    if score >= 80:
        return "strong_watch"
    if score >= 60:
        return "watch"
    if score >= 40:
        return "neutral"
    if score >= 20:
        return "weak"
    return "avoid"
