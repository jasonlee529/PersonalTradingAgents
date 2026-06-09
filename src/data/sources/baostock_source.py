import asyncio
import logging
from typing import Optional

from src.data.sources.base import DataSource

logger = logging.getLogger(__name__)

_baostock_available = False
try:
    import baostock as bs

    _baostock_available = True
except ImportError:
    pass


class BaoStockSource(DataSource):
    """A-share K-line fallback via BaoStock when AKShare is blocked."""

    name = "baostock"

    def __init__(self):
        self._logged_in = False

    def _ensure_login(self) -> bool:
        if not _baostock_available:
            return False
        if self._logged_in:
            return True
        try:
            lg = bs.login()
            if lg.error_code == "0":
                self._logged_in = True
                logger.info("BaoStock login success")
                return True
            logger.warning("BaoStock login failed: %s", lg.error_msg)
        except Exception as e:
            logger.warning("BaoStock login error: %s", e)
        return False

    @staticmethod
    def _to_bs_code(symbol: str) -> str:
        code = str(symbol).zfill(6)
        if code.startswith(("60", "68", "90")):
            return f"sh.{code}"
        return f"sz.{code}"

    async def get_quote(self, symbol: str) -> Optional[dict]:
        kline = await self.get_kline(symbol, limit=1)
        if not kline:
            return None
        latest = kline[-1]
        return {
            "symbol": symbol,
            "price": latest["close"],
            "open": latest["open"],
            "high": latest["high"],
            "low": latest["low"],
            "prev_close": latest["close"],
            "volume": latest["volume"],
            "turnover": latest["turnover"],
            "change_pct": latest["change_pct"],
            "source": self.name,
        }

    async def get_kline(
        self, symbol: str, period: str = "1d", limit: int = 60
    ) -> Optional[list[dict]]:
        if not _baostock_available:
            return None

        def _fetch():
            if not self._ensure_login():
                return None

            code = self._to_bs_code(symbol)
            freq = "d" if period == "1d" else "w" if period == "1w" else "d"

            rs = bs.query_history_k_data_plus(
                code,
                "date,open,high,low,close,preclose,volume,amount,pctChg,turn",
                start_date="2020-01-01",
                end_date="2030-01-01",
                frequency=freq,
                adjustflag="3",
            )

            if rs is None:
                logger.warning("BaoStock query returned None")
                return None

            if rs.error_code != "0":
                logger.warning("BaoStock query failed: %s", rs.error_msg)
                return None

            records = []
            while rs.error_code == "0" and rs.next():
                row = rs.get_row_data()
                records.append(
                    {
                        "date": row[0],
                        "open": float(row[1]) if row[1] else 0.0,
                        "high": float(row[2]) if row[2] else 0.0,
                        "low": float(row[3]) if row[3] else 0.0,
                        "close": float(row[4]) if row[4] else 0.0,
                        "volume": int(float(row[6])) if row[6] else 0,
                        "turnover": float(row[7]) if row[7] else 0.0,
                        "change_pct": float(row[8]) if row[8] else 0.0,
                        "amplitude": 0.0,
                        "change_amt": 0.0,
                        "turnover_rate": float(row[9]) if row[9] else 0.0,
                    }
                )

            return records[-limit:] if records else None

        try:
            return await asyncio.to_thread(_fetch)
        except Exception as e:
            logger.warning("BaoStock get_kline error: %s", e)
            return None

    async def get_fundamentals(self, symbol: str) -> Optional[dict]:
        return None

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

