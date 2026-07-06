from __future__ import annotations

import os
import subprocess
from typing import Any

from crypto_signal_agent import __version__
from crypto_signal_agent.config import Settings
from crypto_signal_agent.models import utc_now_iso
from crypto_signal_agent.presentation import exchange_label
from crypto_signal_agent.storage.sqlite_store import SignalStore


SUPPORTED_MONITOR_EXCHANGES = ("bybit", "binance")


def build_diagnostics_payload(
    settings: Settings,
    store: SignalStore,
    monitor_exchanges: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    exchanges = monitor_exchanges or settings.monitor_exchanges
    count_exchanges = tuple(dict.fromkeys((*exchanges, *settings.required_exchanges, *SUPPORTED_MONITOR_EXCHANGES)))
    recent_signals = store.recent_signals(limit=3)
    return {
        "создано": utc_now_iso(),
        "версия": __version__,
        "коммит": current_commit(),
        "режим": "monitor-new",
        "котировка": settings.quote_asset,
        "основная_биржа": exchange_label(settings.primary_exchange),
        "обязательные_биржи": [exchange_label(exchange) for exchange in settings.required_exchanges],
        "строгий_режим": settings.require_all_exchanges,
        "мониторинг_бирж": [exchange_label(exchange) for exchange in exchanges],
        "интервал_сек": settings.monitor_interval_seconds,
        "база": str(settings.database_path),
        "известные_пары": {
            exchange_label(exchange): store.known_count(exchange) for exchange in count_exchanges
        },
        "сигналов_в_базе": store.signal_count(),
        "telegram_алертов_отправлено": store.sent_alert_count("telegram"),
        "telegram_настроен": bool(settings.telegram_bot_token and settings.telegram_chat_id),
        "openai_настроен": bool(settings.openai_api_key),
        "live_trading": settings.live_trading_enabled,
        "риск": {
            "max_spread_pct": settings.max_spread_pct,
            "min_volume_ratio_vs_7d": settings.min_volume_ratio_vs_7d,
            "min_liquidity_ok": settings.min_liquidity_ok,
            "block_unverified_source": settings.no_signal_if_source_unverified,
        },
        "последние_сигналы": [
            {
                "id": signal.get("id_сигнала"),
                "монета": signal.get("монета"),
                "событие": signal.get("событие"),
                "сигнал": signal.get("сигнал"),
                "риск": (signal.get("риск") or {}).get("уровень"),
                "создано": signal.get("создано"),
            }
            for signal in recent_signals
        ],
    }


def format_diagnostics_message(payload: dict[str, Any]) -> str:
    known = payload["известные_пары"]
    known_text = ", ".join(f"{exchange}: {count}" for exchange, count in known.items())
    recent = payload["последние_сигналы"]
    recent_lines = []
    for signal in recent:
        recent_lines.append(
            f"- #{signal['id']} {signal['монета']}: {signal['сигнал']}, риск={signal['риск']}, {signal['создано']}"
        )
    if not recent_lines:
        recent_lines.append("- нет")

    strict_text = "да" if payload["строгий_режим"] else "нет"
    telegram_text = "да" if payload["telegram_настроен"] else "нет"
    openai_text = "да" if payload["openai_настроен"] else "нет"
    live_text = "да" if payload["live_trading"] else "нет"
    return (
        "Данные для Codex\n"
        f"Время: {payload['создано']}\n"
        f"Версия: {payload['версия']} | Коммит: {payload['коммит']}\n"
        f"Режим: {payload['режим']} | Интервал: {payload['интервал_сек']} сек\n"
        f"Мониторинг: {', '.join(payload['мониторинг_бирж'])}\n"
        f"Котировка: {payload['котировка']}\n"
        f"Основная биржа: {payload['основная_биржа']}\n"
        f"Обязательные биржи: {', '.join(payload['обязательные_биржи'])}\n"
        f"Строгий режим: {strict_text}\n"
        f"База: {payload['база']}\n"
        f"Известные пары: {known_text}\n"
        f"Сигналов в базе: {payload['сигналов_в_базе']}\n"
        f"Telegram алертов отправлено: {payload['telegram_алертов_отправлено']}\n"
        f"Telegram настроен: {telegram_text}\n"
        f"OpenAI настроен: {openai_text}\n"
        f"Live trading: {live_text}\n"
        "Риск-фильтры: "
        f"spread<={payload['риск']['max_spread_pct']}%, "
        f"volume>={payload['риск']['min_volume_ratio_vs_7d']}x, "
        f"liquidity_ok={payload['риск']['min_liquidity_ok']}, "
        f"official_source={payload['риск']['block_unverified_source']}\n"
        "Последние сигналы:\n"
        + "\n".join(recent_lines)
    )


def current_commit() -> str:
    for name in (
        "GIT_COMMIT",
        "GITHUB_SHA",
        "RENDER_GIT_COMMIT",
        "SOURCE_VERSION",
        "HEROKU_SLUG_COMMIT",
        "VERCEL_GIT_COMMIT_SHA",
        "COMMIT_SHA",
    ):
        value = os.getenv(name)
        if value:
            return value[:12]

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            text=True,
            capture_output=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"
