import asyncio
import logging
from typing import Optional

from src.data.sources.base import DataSource
from src.utils.ticker import normalize_ticker

logger = logging.getLogger(__name__)


class AkshareSource(DataSource):
    """A-share financial statements via AKShare domestic adapters."""

    name = "akshare"

    _THS_METHODS = {
        "balance_sheet": "stock_financial_debt_ths",
        "income_statement": "stock_financial_benefit_ths",
        "cashflow": "stock_financial_cash_ths",
    }

    @staticmethod
    def _records_from_frame(df, limit: int = 20) -> list[dict]:
        if df is None or getattr(df, "empty", True):
            return []
        frame = df.head(limit).copy()
        frame = frame.where(frame.notna(), None)
        return frame.to_dict(orient="records")

    def _fetch_ths_statement(
        self, code: str, statement_type: str, freq: str = "quarterly"
    ) -> list[dict]:
        import akshare as ak

        method_name = self._THS_METHODS[statement_type]
        method = getattr(ak, method_name)
        indicator = "按报告期" if freq == "quarterly" else "按年度"
        df = method(symbol=code, indicator=indicator)
        records = self._records_from_frame(df)
        return [{"source": self.name, **item} for item in records]

    async def _get_statement(
        self, symbol: str, statement_type: str, freq: str = "quarterly"
    ) -> Optional[list[dict]]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            records = await asyncio.to_thread(
                self._fetch_ths_statement, code, statement_type, freq
            )
            return records or None
        except Exception as e:
            logger.warning("AKShare %s failed for %s: %s", statement_type, code, e)
            return None

    async def get_balance_sheet(
        self, symbol: str, freq: str = "quarterly"
    ) -> Optional[list[dict]]:
        return await self._get_statement(symbol, "balance_sheet", freq)

    async def get_cashflow(
        self, symbol: str, freq: str = "quarterly"
    ) -> Optional[list[dict]]:
        return await self._get_statement(symbol, "cashflow", freq)

    async def get_income_statement(
        self, symbol: str, freq: str = "quarterly"
    ) -> Optional[list[dict]]:
        return await self._get_statement(symbol, "income_statement", freq)

    async def get_quote(self, symbol: str) -> Optional[dict]:
        return None

    async def get_kline(
        self, symbol: str, period: str = "1d", limit: int = 60
    ) -> Optional[list[dict]]:
        return None

    async def get_fundamentals(self, symbol: str) -> Optional[dict]:
        return None
