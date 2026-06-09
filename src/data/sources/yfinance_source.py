import asyncio
import logging
from typing import Optional

import yfinance as yf
import pandas as pd

from src.config import Settings
from src.data.sources.base import DataSource

logger = logging.getLogger(__name__)


class YFinanceSource(DataSource):
    """US/HK stock data via yfinance."""

    name = "yfinance"

    def __init__(self, settings: Settings):
        self.timeout = getattr(settings, "yfinance_timeout", 30)

    async def _run(self, fn, *args, **kwargs):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fn, *args, **kwargs),
                timeout=self.timeout,
            )
        except Exception as e:
            logger.warning(f"yfinance call failed: {e}")
            return None

    async def get_quote(self, symbol: str) -> Optional[dict]:
        ticker = yf.Ticker(symbol)
        info = await self._run(lambda: ticker.info)
        if not info:
            return None
        return {
            "symbol": symbol,
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "open": info.get("open") or info.get("regularMarketOpen"),
            "high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
            "low": info.get("dayLow") or info.get("regularMarketDayLow"),
            "prev_close": info.get("previousClose") or info.get("regularMarketPreviousClose"),
            "volume": info.get("volume") or info.get("regularMarketVolume"),
            "change_pct": info.get("regularMarketChangePercent"),
            "source": self.name,
        }

    async def get_kline(
        self, symbol: str, period: str = "1d", limit: int = 60
    ) -> Optional[list[dict]]:
        ticker = yf.Ticker(symbol)
        # yfinance period: 1mo, 3mo, 6mo, 1y
        yf_period = "6mo" if limit <= 120 else "1y"
        hist = await self._run(lambda: ticker.history(period=yf_period))
        if hist is None or hist.empty:
            return None

        hist = hist.tail(limit)
        records = []
        for date, row in hist.iterrows():
            records.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            })
        return records

    async def get_fundamentals(self, symbol: str) -> Optional[dict]:
        ticker = yf.Ticker(symbol)
        info = await self._run(lambda: ticker.info)
        if not info:
            return None
        return {
            "symbol": symbol,
            "pe_ttm": info.get("trailingPE"),
            "pe_forward": info.get("forwardPE"),
            "pb": info.get("priceToBook"),
            "roe": info.get("returnOnEquity"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_growth": info.get("earningsGrowth"),
            "debt_ratio": info.get("debtToEquity"),
            "market_cap": info.get("marketCap"),
            "source": self.name,
        }

    # ---- Financial statements ----
    async def get_balance_sheet(self, symbol: str, freq: str = "quarterly") -> Optional[list[dict]]: return None
    async def get_cashflow(self, symbol: str, freq: str = "quarterly") -> Optional[list[dict]]: return None
    async def get_income_statement(self, symbol: str, freq: str = "quarterly") -> Optional[list[dict]]: return None

    # ---- News ----
    async def get_news(self, symbol: str, start_date: str = "", end_date: str = "", limit: int = 20) -> Optional[list[dict]]: return None
    async def get_global_news(self, look_back_days: int = 7, limit: int = 10) -> Optional[list[dict]]: return None

    # ---- Signal stubs ----
    async def fetch_consensus_expectations(self, symbol: str) -> Optional[dict]: return None
    async def fetch_market_heatmap(self, date: str = "") -> Optional[list[dict]]: return None
    async def fetch_cross_border_flow(self, include_history: bool = False) -> Optional[dict]: return None
    async def fetch_theme_exposure(self, symbol: str) -> Optional[list[dict]]: return None
    async def fetch_order_flow_profile(self, symbol: str, include_history: bool = True) -> Optional[dict]: return None
    async def fetch_trading_seat_activity(self, symbol: str, trade_date: str = "", look_back_days: int = 30) -> Optional[dict]: return None
    async def fetch_supply_unlock_schedule(self, symbol: str, trade_date: str = "", forward_days: int = 90) -> Optional[list[dict]]: return None
    async def fetch_peer_industry_snapshot(self, symbol: str, top_n: int = 20) -> Optional[list[dict]]: return None

