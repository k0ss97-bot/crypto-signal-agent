from __future__ import annotations

from dataclasses import asdict, dataclass

from crypto_signal_agent.config import Settings
from crypto_signal_agent.models import VenueAvailability, utc_now_iso
from crypto_signal_agent.presentation import exchange_label, user_venue_dict


@dataclass(frozen=True)
class AssetScanResult:
    asset: str
    status: str
    decision: str
    venues: tuple[VenueAvailability, ...]
    blocks: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_user_dict(self) -> dict:
        return {
            "монета": self.asset,
            "статус": self.status,
            "решение": self.decision,
            "биржи": [user_venue_dict(venue) for venue in self.venues],
            "блокировки": list(self.blocks),
            "предупреждения": list(self.warnings),
        }


def parse_assets(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None or value.strip() == "":
        return default
    seen: set[str] = set()
    assets: list[str] = []
    for raw_item in value.split(","):
        item = raw_item.strip().upper()
        if not item or item in seen:
            continue
        seen.add(item)
        assets.append(item)
    return tuple(assets)


def evaluate_asset_scan(
    settings: Settings,
    asset: str,
    venues: tuple[VenueAvailability, ...],
) -> AssetScanResult:
    blocks: list[str] = []
    warnings: list[str] = []

    primary = next((venue for venue in venues if venue.exchange == settings.primary_exchange), None)
    if primary is None:
        blocks.append(f"основная биржа не проверена: {exchange_label(settings.primary_exchange)}")
    elif not primary.available:
        blocks.append(
            f"спот-пара недоступна на основной бирже: {exchange_label(primary.exchange)} {primary.symbol}"
        )

    missing_confirmation = [
        venue for venue in venues if venue.exchange != settings.primary_exchange and not venue.available
    ]
    if settings.require_all_exchanges and missing_confirmation:
        names = ", ".join(f"{exchange_label(venue.exchange)} {venue.symbol}" for venue in missing_confirmation)
        blocks.append(f"нет обязательной биржи: {names}")
    elif missing_confirmation:
        names = ", ".join(f"{exchange_label(venue.exchange)} {venue.symbol}" for venue in missing_confirmation)
        warnings.append(f"нет подтверждения на бирже: {names}")

    if blocks:
        status = "заблокировано"
        decision = "не добавлять в торговые сигналы"
    elif warnings:
        status = "доступно с предупреждением"
        decision = "можно наблюдать, но без подтверждения на всех биржах"
    else:
        status = "доступно"
        decision = "можно добавлять в наблюдение"

    return AssetScanResult(
        asset=asset.upper(),
        status=status,
        decision=decision,
        venues=venues,
        blocks=tuple(blocks),
        warnings=tuple(warnings),
    )


def build_scan_payload(results: tuple[AssetScanResult, ...], strict: bool) -> dict:
    available = sum(1 for item in results if item.status == "доступно")
    warning = sum(1 for item in results if item.status == "доступно с предупреждением")
    blocked = sum(1 for item in results if item.status == "заблокировано")
    return {
        "создано": utc_now_iso(),
        "режим": "строгий: Bybit и Binance обязательны" if strict else "мягкий: Bybit обязателен, Binance предупреждение",
        "проверено_монет": len(results),
        "доступно": available,
        "с_предупреждением": warning,
        "заблокировано": blocked,
        "монеты": [item.to_user_dict() for item in results],
    }


def format_scan_message(payload: dict) -> str:
    lines = [
        "Проверка монет Crypto Signal Agent",
        f"Время проверки: {payload['создано']}",
        f"Режим: {payload['режим']}",
        (
            f"Итог: проверено {payload['проверено_монет']}, "
            f"доступно {payload['доступно']}, "
            f"с предупреждением {payload['с_предупреждением']}, "
            f"заблокировано {payload['заблокировано']}"
        ),
        "",
    ]
    for item in payload["монеты"]:
        venues = ", ".join(
            f"{venue['сервис']} {venue['пара']}: {venue['доступна']}" for venue in item["биржи"]
        )
        lines.append(f"{item['монета']}: {item['статус']} — {item['решение']}")
        lines.append(f"Биржи: {venues}")
        if item["блокировки"]:
            lines.append("Блокировки: " + "; ".join(item["блокировки"]))
        if item["предупреждения"]:
            lines.append("Предупреждения: " + "; ".join(item["предупреждения"]))
        lines.append("")
    return "\n".join(lines).strip()


def scan_result_to_dict(result: AssetScanResult) -> dict:
    return asdict(result)
