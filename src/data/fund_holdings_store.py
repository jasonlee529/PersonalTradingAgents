import logging
from pathlib import Path
from typing import Optional

import aiosqlite

from src.config import Settings

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS fund_holdings (
    symbol TEXT NOT NULL,
    fund_code TEXT NOT NULL,
    fund_name TEXT DEFAULT '',
    hold_ratio REAL DEFAULT 0.0,
    period TEXT NOT NULL,
    is_new INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT '',
    PRIMARY KEY (symbol, fund_code, period)
);
CREATE INDEX IF NOT EXISTS idx_fh_symbol_period
    ON fund_holdings(symbol, period);
CREATE INDEX IF NOT EXISTS idx_fh_fund_period
    ON fund_holdings(fund_code, period);
CREATE INDEX IF NOT EXISTS idx_fh_is_new
    ON fund_holdings(period, is_new);
"""


class FundHoldingsStore:
    """Persistent local storage for fund portfolio holdings.

    Caches which funds hold a given stock, their holding ratio,
    and whether the position is new for the reporting period.
    Designed for Tushare Pro fund_portfolio data fed by a background job.
    """

    def __init__(self, settings: Settings):
        self.db_path = getattr(
            settings, "fund_holdings_db_path", settings.data_dir / "fund_holdings.db"
        )
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def save_holdings(
        self,
        symbol: str,
        holdings: list[dict],
        period: str,
    ) -> int:
        """Upsert holdings for a symbol + period. Returns rows written."""
        if not holdings:
            return 0

        rows = []
        for h in holdings:
            rows.append((
                symbol,
                h.get("fund_code", ""),
                h.get("fund_name", ""),
                float(h.get("hold_ratio", 0.0) or 0.0),
                period,
                int(h.get("is_new", 0)),
                h.get("updated_at", ""),
            ))

        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                """INSERT OR REPLACE INTO fund_holdings
                (symbol, fund_code, fund_name, hold_ratio, period, is_new, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            await db.commit()

        logger.debug("Saved %d fund holdings for %s/%s", len(rows), symbol, period)
        return len(rows)

    async def get_fund_holders(
        self,
        symbol: str,
        period: Optional[str] = None,
        min_hold_ratio: float = 0.0,
    ) -> list[dict]:
        """Return funds that hold the given stock.

        Args:
            symbol: Stock ticker.
            period: Reporting period e.g. '2026Q1'. If None, latest period.
            min_hold_ratio: Filter by minimum hold ratio.
        """
        if period is None:
            period = await self._latest_period()
            if period is None:
                return []

        query = """SELECT fund_code, fund_name, hold_ratio, period, is_new, updated_at
                   FROM fund_holdings
                   WHERE symbol = ? AND period = ? AND hold_ratio >= ?
                   ORDER BY hold_ratio DESC"""

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (symbol, period, min_hold_ratio)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_holdings_by_fund(
        self,
        fund_code: str,
        period: Optional[str] = None,
    ) -> list[dict]:
        """Return stocks held by a specific fund."""
        if period is None:
            period = await self._latest_period()
            if period is None:
                return []

        query = """SELECT symbol, fund_name, hold_ratio, period, is_new, updated_at
                   FROM fund_holdings
                   WHERE fund_code = ? AND period = ?
                   ORDER BY hold_ratio DESC"""

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (fund_code, period)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_new_holdings(
        self,
        period: Optional[str] = None,
        min_hold_ratio: float = 0.0,
    ) -> list[dict]:
        """Return all new positions (is_new=1) for a period."""
        if period is None:
            period = await self._latest_period()
            if period is None:
                return []

        query = """SELECT symbol, fund_code, fund_name, hold_ratio, period, updated_at
                   FROM fund_holdings
                   WHERE period = ? AND is_new = 1 AND hold_ratio >= ?
                   ORDER BY hold_ratio DESC"""

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (period, min_hold_ratio)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_periods(self) -> list[str]:
        """Return all distinct periods, newest first."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT DISTINCT period FROM fund_holdings ORDER BY period DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [r[0] for r in rows]

    async def _latest_period(self) -> Optional[str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT MAX(period) FROM fund_holdings"
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] else None

    async def delete_period(self, period: str) -> int:
        """Delete all holdings for a period. Returns rows deleted."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "DELETE FROM fund_holdings WHERE period = ?", (period,)
            ) as cursor:
                await db.commit()
                return cursor.rowcount
