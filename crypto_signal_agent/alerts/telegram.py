from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from crypto_signal_agent.config import Settings
from crypto_signal_agent.http_client import HttpClientError, JsonHttpClient
from crypto_signal_agent.models import Signal
from crypto_signal_agent.presentation import (
    bias_label,
    decision_label,
    event_type_label,
    risk_label,
    signal_label,
    venue_label,
)


@dataclass
class TelegramAlerter:
    settings: Settings
    http: JsonHttpClient

    @classmethod
    def from_settings(cls, settings: Settings) -> "TelegramAlerter":
        return cls(settings=settings, http=JsonHttpClient())

    def enabled(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    def send_signal(self, signal: Signal) -> bool:
        return self.send_text(format_signal_message(signal))

    def send_text(self, text: str) -> bool:
        if not self.enabled():
            return False
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        try:
            self.http.post_json(
                url,
                {
                    "chat_id": self.settings.telegram_chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
        except HttpClientError:
            return self._send_signal_with_curl(url, text)
        return True

    def _send_signal_with_curl(self, url: str, text: str) -> bool:
        command = [
            "curl",
            "-sS",
            "-X",
            "POST",
            url,
            "-d",
            f"chat_id={self.settings.telegram_chat_id}",
            "--data-urlencode",
            f"text={text}",
            "-d",
            "disable_web_page_preview=true",
        ]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode != 0:
            return False
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return False
        return bool(payload.get("ok"))


def format_signal_message(signal: Signal) -> str:
    event = signal.event
    venues = ", ".join(venue_label(venue) for venue in signal.venues)
    blocks = "\n".join(f"- {block}" for block in signal.risk.blocks) or "- нет"
    warnings = "\n".join(f"- {warning}" for warning in signal.risk.warnings) or "- нет"
    return (
        f"Событие: {event.asset_upper} / {event_type_label(event.event_type)}\n"
        f"Сигнал: {signal_label(signal.signal)} | Направление: {bias_label(signal.bias)}\n"
        f"Оценка: {signal.score.score}/100 | Риск: {risk_label(signal.risk.risk)}\n"
        f"Решение: {decision_label(signal.decision)}\n"
        f"Биржи: {venues}\n"
        f"Блокировки:\n{blocks}\n"
        f"Предупреждения:\n{warnings}\n"
        f"Источник: {event.source.name} {event.source.url}"
    )
