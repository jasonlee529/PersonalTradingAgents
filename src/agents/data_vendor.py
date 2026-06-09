import asyncio
import logging
from typing import Optional

import pandas as pd

from src.utils.ticker import normalize_ticker

logger = logging.getLogger(__name__)


class DataVendor:
    """Sync wrapper around async DataCollector for TradingAgents integration."""

    def __init__(self, collector):
        self._collector = collector

    def _run(self, coro):
        """Run an async coroutine synchronously.

        Uses asyncio.run when no loop is running (typical thread).
        When called from inside an async context (e.g. tests with running loop),
        uses nest_asyncio to allow nested execution.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop running — safe to use asyncio.run
            return asyncio.run(coro)

        # Loop is running — use nest_asyncio if available
        try:
            import nest_asyncio
            nest_asyncio.apply(loop)
            return loop.run_until_complete(coro)
        except ImportError:
            # Fallback: schedule on the running loop and block
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=60)

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        """Get OHLCV data as CSV string."""
        code = normalize_ticker(symbol)
        try:
            kline = self._run(self._collector.get_kline(code, period="1d", limit=800))
            if not kline:
                return f"No K-line data found for {code}"
            df = pd.DataFrame(kline)
            df["date"] = pd.to_datetime(df["date"])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)]
            if df.empty:
                return f"No data for {code} between {start_date} and {end_date}"
            df = df.rename(
                columns={
                    "date": "Date",
                    "open": "Open",
                    "high": "High",
                    "low": "Low",
                    "close": "Close",
                    "volume": "Volume",
                }
            )
            df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
            csv = df[["Date", "Open", "High", "Low", "Close", "Volume"]].to_csv(index=False)
            header = f"# Stock data for {code} from {start_date} to {end_date}\n# Total records: {len(df)}\n\n"
            return header + csv
        except Exception as e:
            logger.warning("DataVendor.get_stock_data failed for %s: %s", code, e)
            return f"Error getting stock data for {code}: {e}"

    def get_indicators(
        self, symbol: str, indicator: str, curr_date: str, look_back_days: int = 30
    ) -> str:
        """Get technical indicators."""
        code = normalize_ticker(symbol)
        try:
            ind = self._run(
                self._collector.get_indicators(code, period="1d", indicator_list=[indicator])
            )
            if not ind:
                return f"No indicator data for {code}"
            return f"## {indicator} for {code}\n\n{ind}"
        except Exception as e:
            return f"Error calculating {indicator} for {code}: {e}"

    def get_fundamentals(self, symbol: str, curr_date: str = None) -> str:
        """Get company fundamentals as formatted string."""
        code = normalize_ticker(symbol)
        try:
            data = self._run(self._collector.get_fundamentals(code))
            if not data:
                return f"No fundamentals data for {code}"
            lines = [f"# Fundamentals for {code}"]
            for k, v in data.items():
                if k != "symbol":
                    lines.append(f"{k}: {v}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error getting fundamentals for {code}: {e}"

    def get_balance_sheet(self, symbol: str, freq: str = "quarterly", curr_date: str = None) -> str:
        code = normalize_ticker(symbol)
        try:
            data = self._run(self._collector.get_balance_sheet(code))
            if not data:
                return f"No balance sheet data for {code}"
            return f"# Balance Sheet for {code}\n\n{data}"
        except Exception as e:
            return f"Error getting balance sheet for {code}: {e}"

    def get_cashflow(self, symbol: str, freq: str = "quarterly", curr_date: str = None) -> str:
        code = normalize_ticker(symbol)
        try:
            data = self._run(self._collector.get_cashflow(code))
            if not data:
                return f"No cashflow data for {code}"
            return f"# Cashflow for {code}\n\n{data}"
        except Exception as e:
            return f"Error getting cashflow for {code}: {e}"

    def get_income_statement(self, symbol: str, freq: str = "quarterly", curr_date: str = None) -> str:
        code = normalize_ticker(symbol)
        try:
            data = self._run(self._collector.get_income_statement(code))
            if not data:
                return f"No income statement data for {code}"
            return f"# Income Statement for {code}\n\n{data}"
        except Exception as e:
            return f"Error getting income statement for {code}: {e}"

    def get_news(self, symbol: str, start_date: str = "", end_date: str = "") -> str:
        code = normalize_ticker(symbol)
        try:
            news = self._run(
                self._collector.get_news(
                    code, start_date=start_date, end_date=end_date, limit=20
                )
            )
            if not news:
                return f"No news found for {code}"
            lines = [f"# News for {code}"]
            for item in news:
                lines.append(
                    f"- [{item.get('time', '')}] {item.get('title', '')} ({item.get('source', '')})"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error getting news for {code}: {e}"

    def get_global_news(self, curr_date: str = None, look_back_days: int = None, limit: int = None) -> str:
        """Get macro/global news.

        TradingAgents tool calls pass (curr_date, look_back_days, limit).
        Older local callers may pass only (look_back_days, limit), so keep
        defaults here and ignore curr_date.
        """
        if isinstance(curr_date, int):
            # Back-compat: get_global_news(look_back_days, limit)
            look_back_days, limit = curr_date, look_back_days
            curr_date = None
        look_back_days = 7 if look_back_days is None else look_back_days
        limit = 10 if limit is None else limit
        try:
            news = self._run(
                self._collector.get_global_news(
                    look_back_days=look_back_days, limit=limit
                )
            )
            if not news:
                return "No global news found"
            lines = ["# Global News"]
            for item in news:
                lines.append(
                    f"- [{item.get('time', '')}] {item.get('title', '')} ({item.get('source', '')})"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error getting global news: {e}"

    def get_insider_transactions(self, symbol: str) -> str:
        """A-share insider transactions not widely available via HTTP; return placeholder."""
        code = normalize_ticker(symbol)
        return (
            f"# Insider Transactions for {code}\n\n"
            "A-share insider transaction data is not available via public HTTP APIs."
        )

    def load_ohlcv(self, symbol: str, curr_date: str) -> pd.DataFrame:
        """Load OHLCV DataFrame for stockstats (Date, Open, High, Low, Close, Volume)."""
        code = normalize_ticker(symbol)
        try:
            kline = self._run(self._collector.get_kline(code, period="1d", limit=800))
            if not kline:
                return pd.DataFrame()
            df = pd.DataFrame(kline)
            df = df.rename(
                columns={
                    "date": "Date",
                    "open": "Open",
                    "high": "High",
                    "low": "Low",
                    "close": "Close",
                    "volume": "Volume",
                }
            )
            df["Date"] = pd.to_datetime(df["Date"])
            cutoff = pd.to_datetime(curr_date)
            return df[df["Date"] <= cutoff]
        except Exception as e:
            logger.warning("DataVendor.load_ohlcv failed for %s: %s", code, e)
            return pd.DataFrame()
