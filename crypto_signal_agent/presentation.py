from __future__ import annotations

from typing import Any

from crypto_signal_agent.models import Signal, VenueAvailability


EXCHANGE_LABELS = {
    "bybit": "Bybit",
    "binance": "Binance",
}

EVENT_TYPE_LABELS = {
    "major_cex_spot_listing": "листинг на крупной спотовой бирже",
    "binance_spot_listing": "спотовый листинг на Binance",
    "bybit_spot_listing": "спотовый листинг на Bybit",
    "coinbase_spot_listing": "спотовый листинг на Coinbase",
    "upbit_spot_listing": "спотовый листинг на Upbit",
    "binance_futures_listing": "фьючерсный листинг на Binance",
    "bybit_futures_listing": "фьючерсный листинг на Bybit",
    "major_cex_futures_listing": "фьючерсный листинг на крупной бирже",
    "delisting": "делистинг",
    "monitoring_tag": "метка повышенного контроля",
    "hack": "взлом",
    "exploit": "эксплойт",
    "security_incident": "инцидент безопасности",
    "legal_negative": "негативная юридическая новость",
}

SCORE_LABELS = {
    "strong_watch": "сильный сигнал для наблюдения",
    "watch": "наблюдать",
    "neutral": "нейтрально",
    "weak": "слабый сигнал",
    "avoid": "избегать",
}

SIGNAL_LABELS = {
    "watch": "наблюдать",
    "sell_risk": "риск продажи или выхода",
    "neutral": "нейтрально",
    "avoid": "избегать",
}

BIAS_LABELS = {
    "long_bias": "склонность к лонгу",
    "sell_bias": "защитный сценарий",
    "no_trade": "без сделки",
}

RISK_LABELS = {
    "low": "низкий",
    "medium": "средний",
    "high": "высокий",
    "blocked": "заблокировано",
}

DECISION_LABELS = {
    "wait_for_pullback_or_confirmation": "ждать откат или подтверждение",
    "watch_not_chase": "наблюдать, не догонять цену",
    "wait_for_better_setup": "ждать более сильный сетап",
    "weak_signal": "слабый сигнал",
    "blocked_by_risk_engine": "заблокировано риск-фильтром",
    "defensive_review": "пересмотреть позицию и риск",
}


def exchange_label(exchange: str) -> str:
    return EXCHANGE_LABELS.get(exchange.lower(), exchange)


def yes_no(value: bool) -> str:
    return "да" if value else "нет"


def event_type_label(event_type: str) -> str:
    return EVENT_TYPE_LABELS.get(event_type.lower(), event_type)


def score_label(label: str) -> str:
    return SCORE_LABELS.get(label, label)


def signal_label(signal: str) -> str:
    return SIGNAL_LABELS.get(signal, signal)


def bias_label(bias: str) -> str:
    return BIAS_LABELS.get(bias, bias)


def risk_label(risk: str) -> str:
    return RISK_LABELS.get(risk, risk)


def decision_label(decision: str) -> str:
    return DECISION_LABELS.get(decision, decision)


def venue_label(venue: VenueAvailability) -> str:
    return f"{exchange_label(venue.exchange)} {venue.symbol}: {yes_no(venue.available)}"


def user_venue_dict(venue: VenueAvailability) -> dict[str, Any]:
    return {
        "сервис": exchange_label(venue.exchange),
        "пара": venue.symbol,
        "рынок": "спот",
        "доступна": yes_no(venue.available),
        "причина": venue.reason,
    }


def user_signal_dict(signal: Signal) -> dict[str, Any]:
    event = signal.event
    return {
        "монета": event.asset_upper,
        "событие": event_type_label(event.event_type),
        "источник": {
            "сервис": event.source.name,
            "сайт": event.source.url,
            "официальный": yes_no(event.source.is_official),
            "опубликовано": event.source.published_at,
        },
        "обнаружено": event.detected_at,
        "биржи": [user_venue_dict(venue) for venue in signal.venues],
        "рынок": {
            "изменение_цены_за_20м_проц": signal.market.price_change_20m_pct,
            "объем_к_среднему_за_7д": signal.market.volume_ratio_vs_7d,
            "спред_проц": signal.market.spread_pct,
            "ликвидность_достаточная": yes_no(signal.market.liquidity_ok),
        },
        "оценка": {
            "баллы": signal.score.score,
            "уровень": score_label(signal.score.label),
            "факторы": list(signal.score.factors),
        },
        "риск": {
            "уровень": risk_label(signal.risk.risk),
            "разрешено": yes_no(signal.risk.allowed),
            "блокировки": list(signal.risk.blocks),
            "предупреждения": list(signal.risk.warnings),
        },
        "сигнал": signal_label(signal.signal),
        "направление": bias_label(signal.bias),
        "уверенность": signal.confidence,
        "решение": decision_label(signal.decision),
        "анализ": signal.analysis,
        "создано": signal.created_at,
    }
