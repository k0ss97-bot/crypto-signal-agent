from __future__ import annotations

from dataclasses import replace

from crypto_signal_agent.alerts.telegram import TelegramAlerter
from crypto_signal_agent.analysis.decision import choose_signal
from crypto_signal_agent.analysis.llm_analyst import LlmAnalyst
from crypto_signal_agent.analysis.risk_engine import evaluate_risk
from crypto_signal_agent.analysis.scoring import score_event
from crypto_signal_agent.config import Settings
from crypto_signal_agent.models import Event, MarketMetrics, Signal, VenueAvailability
from crypto_signal_agent.storage.sqlite_store import SignalStore


class SignalPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SignalStore(settings.database_path)
        self.alerter = TelegramAlerter.from_settings(settings)
        self.llm = LlmAnalyst(settings)
        self.last_alert_sent: bool | None = None

    def analyze(
        self,
        event: Event,
        market: MarketMetrics,
        venues: tuple[VenueAvailability, ...],
        send_alert: bool = False,
    ) -> Signal:
        score = score_event(event, market, venues)
        risk = evaluate_risk(self.settings, event, market, venues)
        signal_name, bias, confidence, decision = choose_signal(score, risk, event.event_type)
        draft = Signal(
            event=event,
            venues=venues,
            market=market,
            score=score,
            risk=risk,
            signal=signal_name,
            bias=bias,
            confidence=confidence,
            decision=decision,
            analysis="",
        )
        analysis = self.llm.explain(draft)
        final_signal = replace(draft, analysis=analysis)
        self.store.save(final_signal)
        if send_alert:
            self.last_alert_sent = self.alerter.send_signal(final_signal)
        else:
            self.last_alert_sent = None
        return final_signal
