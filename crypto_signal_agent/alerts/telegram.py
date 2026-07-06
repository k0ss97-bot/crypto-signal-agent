from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

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


DIAGNOSTICS_CALLBACK_DATA = "codex_diagnostics_v1"


def diagnostics_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "Данные для Codex",
                    "callback_data": DIAGNOSTICS_CALLBACK_DATA,
                }
            ]
        ]
    }


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

    def send_text(
        self,
        text: str,
        chat_id: str | int | None = None,
        reply_markup: dict[str, Any] | None = None,
        include_diagnostics_button: bool = True,
    ) -> bool:
        if not self.enabled():
            return False
        target_chat_id = chat_id or self.settings.telegram_chat_id
        payload: dict[str, Any] = {
            "chat_id": target_chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        elif include_diagnostics_button:
            payload["reply_markup"] = diagnostics_keyboard()

        url = self._api_url("sendMessage")
        try:
            response = self.http.post_json(url, payload)
        except HttpClientError:
            return self._post_with_curl(url, payload)
        return bool(response.get("ok", True)) if isinstance(response, dict) else True

    def fetch_updates(self, offset: int | None = None, timeout_seconds: int = 0) -> tuple[dict[str, Any], ...]:
        if not self.settings.telegram_bot_token:
            return ()
        params: dict[str, Any] = {
            "timeout": timeout_seconds,
            "allowed_updates": json.dumps(["callback_query", "message"]),
        }
        if offset is not None:
            params["offset"] = offset
        try:
            payload = self.http.get_json(self._api_url("getUpdates"), params=params)
        except HttpClientError:
            return ()
        if not isinstance(payload, dict) or not payload.get("ok"):
            return ()
        updates = payload.get("result") or []
        return tuple(update for update in updates if isinstance(update, dict))

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> bool:
        if not self.settings.telegram_bot_token:
            return False
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        try:
            response = self.http.post_json(self._api_url("answerCallbackQuery"), payload)
        except HttpClientError:
            return self._post_with_curl(self._api_url("answerCallbackQuery"), payload)
        return bool(response.get("ok", True)) if isinstance(response, dict) else True

    def delete_webhook(self) -> bool:
        if not self.settings.telegram_bot_token:
            return False
        try:
            response = self.http.post_json(self._api_url("deleteWebhook"), {"drop_pending_updates": False})
        except HttpClientError:
            return self._post_with_curl(self._api_url("deleteWebhook"), {"drop_pending_updates": False})
        return bool(response.get("ok", True)) if isinstance(response, dict) else True

    def is_authorized_chat(self, chat_id: str | int | None) -> bool:
        if chat_id is None or not self.settings.telegram_chat_id:
            return False
        return str(chat_id) == str(self.settings.telegram_chat_id)

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/{method}"

    def _post_with_curl(self, url: str, payload: dict[str, Any]) -> bool:
        command = [
            "curl",
            "-sS",
            "-X",
            "POST",
            url,
            "-H",
            "Content-Type: application/json",
            "--data",
            json.dumps(payload, ensure_ascii=False),
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
