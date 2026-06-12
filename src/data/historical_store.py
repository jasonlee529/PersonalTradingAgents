import asyncio
import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

import aiosqlite

from src.config import Settings

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS kline_history (
    symbol TEXT NOT NULL,
    period TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    turnover REAL DEFAULT 0.0,
    amplitude REAL DEFAULT 0.0,
    change_pct REAL DEFAULT 0.0,
    change_amt REAL DEFAULT 0.0,
    turnover_rate REAL DEFAULT 0.0,
    PRIMARY KEY (symbol, period, date)
);
CREATE INDEX IF NOT EXISTS idx_kline_symbol_period_date
    ON kline_history(symbol, period, date);
"""


class HistoricalDataStore:
    """Persistent local storage for historical K-line data.

    Stores OHLCV records per (symbol, period) in SQLite.
    Supports UPSERT so repeated saves overwrite existing rows.
    """

    def __init__(self, settings: Settings):
        self.db_path = getattr(settings, "historical_db_path", settings.data_dir / "historical.db")
        # Ensure parent directory exists so SQLite can create the file
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()
        self._initialized = True

    async def ensure_db(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            await self.init_db()

    async def save_kline(self, symbol: str, period: str, records: list[dict]) -> None:
        if not records:
            return
        await self.ensure_db()
        rows = []
        for r in records:
            rows.append((
                symbol, period, r.get("date", ""),
                r.get("open", 0.0), r.get("high", 0.0), r.get("low", 0.0),
                r.get("close", 0.0), r.get("volume", 0),
                r.get("turnover", 0.0), r.get("amplitude", 0.0),
                r.get("change_pct", 0.0), r.get("change_amt", 0.0),
                r.get("turnover_rate", 0.0),
            ))
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                """INSERT OR REPLACE INTO kline_history
                (symbol, period, date, open, high, low, close, volume,
                 turnover, amplitude, change_pct, change_amt, turnover_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            await db.commit()
        logger.debug("Saved %d kline rows for %s/%s", len(rows), symbol, period)

    async def load_kline(
        self, symbol: str, period: str,
        start_date: str = "", end_date: str = "",
    ) -> Optional[list[dict]]:
        await self.ensure_db()
        query = """SELECT date, open, high, low, close, volume,
                   turnover, amplitude, change_pct, change_amt, turnover_rate
                   FROM kline_history WHERE symbol = ? AND period = ?"""
        params = [symbol, period]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date"

        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    if not rows:
                        return None
                    return [dict(r) for r in rows]
        except sqlite3.OperationalError as exc:
            if "no such table: kline_history" not in str(exc).lower():
                raise
            await self.init_db()
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    if not rows:
                        return None
                    return [dict(r) for r in rows]

    async def get_date_range(self, symbol: str, period: str) -> tuple[Optional[str], Optional[str]]:
        await self.ensure_db()
        query = "SELECT MIN(date), MAX(date) FROM kline_history WHERE symbol = ? AND period = ?"
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(query, (symbol, period)) as cursor:
                    row = await cursor.fetchone()
                    return (row[0], row[1]) if row else (None, None)
        except sqlite3.OperationalError as exc:
            if "no such table: kline_history" not in str(exc).lower():
                raise
            await self.init_db()
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(query, (symbol, period)) as cursor:
                    row = await cursor.fetchone()
                    return (row[0], row[1]) if row else (None, None)
