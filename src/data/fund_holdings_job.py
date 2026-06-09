"""Background job to refresh fund portfolio holdings from Tushare Pro.

Rate limit: 30 requests / 20 seconds (~0.67s between requests).
Retry: 3 attempts with exponential backoff, then skip.
Tushare is an optional dependency; if unavailable the job logs a warning and exits.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.config import Settings
from src.data.fund_holdings_store import FundHoldingsStore

logger = logging.getLogger(__name__)

# Rate limit: 30 requests per 20 seconds
_MIN_INTERVAL_SEC = 20.0 / 30.0
_MAX_RETRIES = 3


def _to_store_period(end_date: str) -> str:
    """Convert Tushare end_date (YYYYMMDD) to store period (YYYYQn)."""
    if len(end_date) != 8:
        return end_date
    year = end_date[:4]
    month = int(end_date[4:6])
    quarter = (month - 1) // 3 + 1
    return f"{year}Q{quarter}"


class FundHoldingsRefreshJob:
    """Pull fund portfolio data from Tushare Pro and cache in FundHoldingsStore."""

    def __init__(
        self,
        settings: Settings,
        store: Optional[FundHoldingsStore] = None,
    ):
        self.settings = settings
        self.store = store or FundHoldingsStore(settings)
        self._pro = None

    def _get_client(self):
        """Lazy-init Tushare Pro client. Returns None if tushare unavailable or no token."""
        if self._pro is not None:
            return self._pro

        try:
            import tushare as ts
        except ImportError:
            logger.warning("Tushare not installed; fund holdings refresh skipped")
            return None

        token = getattr(self.settings, "tushare_api_key", "")
        if not token:
            logger.warning("tushare_api_key not configured; fund holdings refresh skipped")
            return None

        self._pro = ts.pro_api(token)
        return self._pro

    async def run(
        self,
        symbols: list[str],
        period: Optional[str] = None,
    ) -> dict:
        """Fetch fund portfolio for given symbols and save to store.

        Args:
            symbols: List of stock symbols (e.g. ["600519", "000001"]).
            period: Optional store period override (e.g. "2026Q1").

        Returns:
            Summary dict with processed/skipped/failed counts.
        """
        pro = self._get_client()
        if pro is None:
            return {"skipped": True, "reason": "tushare_unavailable"}

        if not symbols:
            return {"processed": 0, "skipped": 0, "failed": 0}

        await self.store.init_db()

        processed = 0
        skipped = 0
        failed = 0

        for symbol in symbols:
            # Convert symbol to Tushare format (add .SH/.SZ/.BJ suffix)
            ts_symbol = self._to_tushare_symbol(symbol)

            result = await self._fetch_one(pro, ts_symbol)
            if result is None:
                failed += 1
            elif not result:
                skipped += 1
            else:
                store_period = period or _to_store_period(result[0].get("end_date", ""))
                if not store_period:
                    store_period = "unknown"
                await self.store.save_holdings(symbol, result, period=store_period)
                processed += 1

            # Rate limiting
            await asyncio.sleep(_MIN_INTERVAL_SEC)

        logger.info(
            "Fund holdings refresh complete: %d processed, %d skipped, %d failed",
            processed, skipped, failed,
        )
        return {"processed": processed, "skipped": skipped, "failed": failed}

    async def _fetch_one(self, pro, ts_symbol: str) -> Optional[list[dict]]:
        """Fetch fund portfolio for one symbol with retries.

        Returns:
            List of holding dicts, or None on failure, or empty list if no data.
        """
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                # Run blocking tushare call in thread pool
                df = await asyncio.to_thread(pro.fund_portfolio, symbol=ts_symbol)
                if df is None or df.empty:
                    return []

                records = []
                for _, row in df.iterrows():
                    records.append({
                        "fund_code": str(row.get("ts_code", "")),
                        "fund_name": "",
                        "hold_ratio": float(row.get("stk_mkv_ratio", 0.0) or 0.0),
                        "end_date": str(row.get("end_date", "")),
                        "is_new": 0,  # Tushare doesn't provide new/existing flag directly
                    })
                return records

            except Exception as e:
                logger.warning(
                    "Fund portfolio fetch %s failed (attempt %d/%d): %s",
                    ts_symbol, attempt, _MAX_RETRIES, e,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(2 ** (attempt - 1))  # 1s, 2s, 4s
                else:
                    return None

        return None

    @staticmethod
    def _to_tushare_symbol(symbol: str) -> str:
        """Append exchange suffix for Tushare Pro.

        Rules:
            - 6xxxxxx -> .SH
            - 0xxxxxx -> .SZ
            - 3xxxxxx -> .SZ
            - 8xxxxxx / 4xxxxxx -> .BJ
        """
        if "." in symbol:
            return symbol
        if symbol.startswith("6"):
            return f"{symbol}.SH"
        if symbol.startswith(("0", "3")):
            return f"{symbol}.SZ"
        return f"{symbol}.BJ"
