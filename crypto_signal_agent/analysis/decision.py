from __future__ import annotations

from crypto_signal_agent.models import RiskDecision, ScoreResult


SELL_RISK_EVENTS = {
    "delisting",
    "monitoring_tag",
    "hack",
    "exploit",
    "security_incident",
    "legal_negative",
}


def choose_signal(score: ScoreResult, risk: RiskDecision, event_type: str = "") -> tuple[str, str, int, str]:
    if not risk.allowed:
        return "avoid", "no_trade", min(score.score, 35), "blocked_by_risk_engine"

    if event_type.lower() in SELL_RISK_EVENTS:
        return "sell_risk", "sell_bias", max(55, 100 - score.score), "defensive_review"

    if score.score >= 80:
        return "watch", "long_bias", min(90, score.score), "wait_for_pullback_or_confirmation"
    if score.score >= 60:
        return "watch", "long_bias", min(80, score.score), "watch_not_chase"
    if score.score >= 40:
        return "neutral", "no_trade", min(65, score.score), "wait_for_better_setup"
    return "avoid", "no_trade", min(45, score.score), "weak_signal"
