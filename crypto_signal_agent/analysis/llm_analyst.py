from __future__ import annotations

import json
from dataclasses import dataclass

from crypto_signal_agent.config import Settings
from crypto_signal_agent.models import Signal
from crypto_signal_agent.presentation import (
    bias_label,
    event_type_label,
    risk_label,
    signal_label,
    user_signal_dict,
    venue_label,
)


SYSTEM_PROMPT = """Ты крипто-аналитик событий.
Ты не даешь финансовых рекомендаций и не исполняешь сделки.
Отвечай только на русском языке.
Не переводи названия сервисов, сайтов, бирж, тикеры и торговые пары.
Объясни событие, доступность бирж, реакцию рынка, оценку, блокировки риска и условия отмены сценария.
Никогда не пиши "покупай сейчас" или "продавай сейчас".
Если риск-фильтр заблокировал сетап, скажи это явно.
Пиши кратко."""


@dataclass
class LlmAnalyst:
    settings: Settings

    def explain(self, draft_signal: Signal) -> str:
        if not self.settings.openai_api_key:
            return fallback_summary(draft_signal)
        try:
            from openai import OpenAI
        except ImportError:
            return fallback_summary(draft_signal)

        client = OpenAI(api_key=self.settings.openai_api_key)
        payload = json.dumps(user_signal_dict(draft_signal), ensure_ascii=False, indent=2)
        try:
            response = client.responses.create(
                model=self.settings.openai_model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": payload},
                ],
            )
        except Exception as exc:  # pragma: no cover - depends on external API
            return f"{fallback_summary(draft_signal)}\n\nАнализ OpenAI пропущен: {exc}"

        text = getattr(response, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        return fallback_summary(draft_signal)


def fallback_summary(signal: Signal) -> str:
    event = signal.event
    venue_text = ", ".join(venue_label(venue) for venue in signal.venues)
    blocks = "; ".join(signal.risk.blocks) if signal.risk.blocks else "нет"
    warnings = "; ".join(signal.risk.warnings) if signal.risk.warnings else "нет"
    action_note = (
        "Если монета уже есть в позиции, пересмотрите риск; не открывайте слепой шорт."
        if signal.signal == "sell_risk"
        else "Не догоняйте цену; используйте это только как сигнал для наблюдения."
    )
    return (
        f"{event.asset_upper} {event_type_label(event.event_type)}: "
        f"сигнал={signal_label(signal.signal)}, направление={bias_label(signal.bias)}, "
        f"оценка={signal.score.score}/100, риск={risk_label(signal.risk.risk)}. "
        f"Биржи: {venue_text}. Блокировки: {blocks}. Предупреждения: {warnings}. "
        f"{action_note}"
    )
