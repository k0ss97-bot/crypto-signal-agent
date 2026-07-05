from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from crypto_signal_agent.models import Signal
from crypto_signal_agent.models import utc_now_iso
from crypto_signal_agent.presentation import user_signal_dict


@dataclass
class SignalStore:
    path: Path

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
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

    def save(self, signal: Signal) -> int:
        self.init()
        payload = json.dumps(user_signal_dict(signal), ensure_ascii=False, sort_keys=True)
        with sqlite3.connect(self.path) as db:
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

    def known_symbols(self, exchange: str) -> set[str]:
        self.init()
        with sqlite3.connect(self.path) as db:
            rows = db.execute(
                "SELECT symbol FROM known_listings WHERE exchange = ?",
                (exchange,),
            ).fetchall()
        return {str(row[0]).upper() for row in rows}

    def known_count(self, exchange: str) -> int:
        self.init()
        with sqlite3.connect(self.path) as db:
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
        with sqlite3.connect(self.path) as db:
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
