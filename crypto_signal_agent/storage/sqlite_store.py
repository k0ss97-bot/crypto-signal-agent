from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterator
from typing import Any

from crypto_signal_agent.models import Signal
from crypto_signal_agent.models import utc_now_iso
from crypto_signal_agent.presentation import user_signal_dict


@contextmanager
def connect_db(path: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(path)) as db:
        with db:
            yield db


@dataclass
class SignalStore:
    path: Path

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with connect_db(self.path) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    bias TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    risk TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_signals_asset_created
                ON signals(asset, created_at)
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS known_listings (
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    base_asset TEXT NOT NULL,
                    quote_asset TEXT NOT NULL,
                    status TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    PRIMARY KEY(exchange, symbol)
                )
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_known_listings_exchange_quote
                ON known_listings(exchange, quote_asset)
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS sent_alerts (
                    channel TEXT NOT NULL,
                    alert_key TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(channel, alert_key)
                )
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sent_alerts_asset_sent
                ON sent_alerts(asset, sent_at)
                """
            )

    def save(self, signal: Signal) -> int:
        self.init()
        payload = json.dumps(user_signal_dict(signal), ensure_ascii=False, sort_keys=True)
        with connect_db(self.path) as db:
            cursor = db.execute(
                """
                INSERT INTO signals (
                    asset, event_type, signal, bias, score, risk, created_at, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.event.asset_upper,
                    signal.event.event_type,
                    signal.signal,
                    signal.bias,
                    signal.score.score,
                    signal.risk.risk,
                    signal.created_at,
                    payload,
                ),
            )
            return int(cursor.lastrowid)

    def recent_signals(self, limit: int = 10, asset: str | None = None) -> list[dict[str, Any]]:
        self.init()
        safe_limit = max(1, min(int(limit), 100))
        params: tuple[object, ...]
        where = ""
        if asset:
            where = "WHERE asset = ?"
            params = (asset.upper(), safe_limit)
        else:
            params = (safe_limit,)
        with connect_db(self.path) as db:
            rows = db.execute(
                f"""
                SELECT id, payload_json
                FROM signals
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        signals: list[dict[str, Any]] = []
        for signal_id, payload_json in rows:
            payload = json.loads(str(payload_json))
            payload["id_сигнала"] = int(signal_id)
            signals.append(payload)
        return signals

    def signal_count(self) -> int:
        self.init()
        with connect_db(self.path) as db:
            row = db.execute("SELECT COUNT(*) FROM signals").fetchone()
        return int(row[0] or 0)

    def alert_key(self, signal: Signal) -> str:
        event = signal.event
        payload = {
            "asset": event.asset_upper,
            "event_type": event.event_type.lower(),
            "source_name": event.source.name.strip().lower(),
            "source_url": event.source.url.strip(),
            "source_published_at": event.source.published_at or "",
        }
        raw_key = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def alert_was_sent(self, channel: str, alert_key: str) -> bool:
        self.init()
        with connect_db(self.path) as db:
            row = db.execute(
                """
                SELECT 1
                FROM sent_alerts
                WHERE channel = ? AND alert_key = ?
                """,
                (channel, alert_key),
            ).fetchone()
        return row is not None

    def record_alert_sent(self, channel: str, alert_key: str, signal: Signal) -> bool:
        self.init()
        payload = json.dumps(user_signal_dict(signal), ensure_ascii=False, sort_keys=True)
        with connect_db(self.path) as db:
            cursor = db.execute(
                """
                INSERT OR IGNORE INTO sent_alerts (
                    channel, alert_key, asset, event_type, sent_at, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    channel,
                    alert_key,
                    signal.event.asset_upper,
                    signal.event.event_type,
                    utc_now_iso(),
                    payload,
                ),
            )
            return cursor.rowcount > 0

    def sent_alert_count(self, channel: str | None = None) -> int:
        self.init()
        if channel:
            with connect_db(self.path) as db:
                row = db.execute(
                    "SELECT COUNT(*) FROM sent_alerts WHERE channel = ?",
                    (channel,),
                ).fetchone()
        else:
            with connect_db(self.path) as db:
                row = db.execute("SELECT COUNT(*) FROM sent_alerts").fetchone()
        return int(row[0] or 0)

    def known_symbols(self, exchange: str) -> set[str]:
        self.init()
        with connect_db(self.path) as db:
            rows = db.execute(
                "SELECT symbol FROM known_listings WHERE exchange = ?",
                (exchange,),
            ).fetchall()
        return {str(row[0]).upper() for row in rows}

    def known_count(self, exchange: str) -> int:
        self.init()
        with connect_db(self.path) as db:
            row = db.execute(
                "SELECT COUNT(*) FROM known_listings WHERE exchange = ?",
                (exchange,),
            ).fetchone()
        return int(row[0] or 0)

    def upsert_listing(
        self,
        exchange: str,
        symbol: str,
        base_asset: str,
        quote_asset: str,
        status: str,
        raw: dict,
    ) -> None:
        self.init()
        now = utc_now_iso()
        with connect_db(self.path) as db:
            db.execute(
                """
                INSERT INTO known_listings (
                    exchange, symbol, base_asset, quote_asset, status,
                    first_seen_at, last_seen_at, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, symbol) DO UPDATE SET
                    status = excluded.status,
                    last_seen_at = excluded.last_seen_at,
                    raw_json = excluded.raw_json
                """,
                (
                    exchange.lower(),
                    symbol.upper(),
                    base_asset.upper(),
                    quote_asset.upper(),
                    status,
                    now,
                    now,
                    json.dumps(raw, ensure_ascii=False, sort_keys=True),
                ),
            )
