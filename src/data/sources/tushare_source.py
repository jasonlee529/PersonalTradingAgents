import asyncio
import logging
from typing import Optional

from src.data.sources.base import DataSource
from src.utils.ticker import normalize_ticker

logger = logging.getLogger(__name__)


class TushareSource(DataSource):
    """Tushare Pro API data source.

    Requires tushare_api_key configured in settings.
    """

    name = "tushare"

    def __init__(self, settings=None):
        self._settings = settings
        self._token = str(getattr(settings, "tushare_api_key", "") or "").strip()
        self._pro = None

    def _get_client(self):
        """Lazy-init Tushare Pro client. Returns None on failure."""
        if self._pro is not None:
            return self._pro
        if not self._token:
            return None
        try:
            import tushare as ts

            self._pro = ts.pro_api(self._token)
            return self._pro
        except ImportError:
            logger.debug("Tushare not installed")
            return None
        except Exception as e:
            logger.debug("Tushare client init failed: %s", e)
            return None

    @staticmethod
    def _to_ts_symbol(symbol: str) -> str:
        """Convert symbol to Tushare format (e.g., 000001 -> 000001.SZ)."""
        code = str(normalize_ticker(symbol)).strip().upper()
        if "." in code:
            return code
        code = code.zfill(6) if code.isdigit() else code
        if code.startswith("6"):
            return f"{code}.SH"
        if code.startswith(("8", "4")):
            return f"{code}.BJ"
        return f"{code}.SZ"

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        try:
            if value is None or value == "":
                return None
            f = float(value)
            return f if f == f else None  # NaN check
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        try:
            if value is None or value == "":
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None

    async def get_quote(self, symbol: str) -> Optional[dict]:
        pro = self._get_client()
        if pro is None:
            return None
        try:
            ts_code = self._to_ts_symbol(symbol)

            def _fetch():
                df = pro.daily(ts_code=ts_code, limit=1)
                if df is None or df.empty:
                    return None
                row = df.iloc[0]
                return {
                    "symbol": str(symbol).zfill(6),
                    "name": "",  # Tushare daily doesn't provide name
                    "price": self._safe_float(row.get("close")),
                    "high": self._safe_float(row.get("high")),
                    "low": self._safe_float(row.get("low")),
                    "open": self._safe_float(row.get("open")),
                    "prev_close": self._safe_float(row.get("pre_close")),
                    "volume": self._safe_int(row.get("vol")),
                    "turnover": self._safe_float(row.get("amount")),
                    "change_pct": self._safe_float(row.get("pct_chg")),
                    "source": self.name,
                }

            return await asyncio.to_thread(_fetch)
        except Exception as e:
            logger.debug("Tushare quote failed for %s: %s", symbol, e)
            return None

    async def get_kline(
        self, symbol: str, period: str = "1d", limit: int = 60
    ) -> Optional[list[dict]]:
        pro = self._get_client()
        if pro is None:
            return None
        try:
            ts_code = self._to_ts_symbol(symbol)

            def _fetch():
                if period == "1d":
                    df = pro.daily(ts_code=ts_code, limit=limit)
                elif period == "1w":
                    df = pro.weekly(ts_code=ts_code, limit=limit)
                elif period == "1M":
                    df = pro.monthly(ts_code=ts_code, limit=limit)
                else:
                    df = pro.daily(ts_code=ts_code, limit=limit)

                if df is None or df.empty:
                    return None

                # Sort by date ascending
                df_sorted = df.sort_values("trade_date", ascending=True)
                results = []
                for _, row in df_sorted.iterrows():
                    dt_str = str(row.get("trade_date", ""))
                    if len(dt_str) == 8:
                        dt_str = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
                    results.append({
                        "date": dt_str,
                        "open": self._safe_float(row.get("open")),
                        "close": self._safe_float(row.get("close")),
                        "high": self._safe_float(row.get("high")),
                        "low": self._safe_float(row.get("low")),
                        "volume": self._safe_int(row.get("vol")),
                        "turnover": self._safe_float(row.get("amount")),
                        "change_pct": self._safe_float(row.get("pct_chg")),
                    })
                return results

            return await asyncio.to_thread(_fetch)
        except Exception as e:
            logger.debug("Tushare kline failed for %s: %s", symbol, e)
            return None

    async def get_fundamentals(self, symbol: str) -> Optional[dict]:
        pro = self._get_client()
        if pro is None:
            return None
        try:
            ts_code = self._to_ts_symbol(symbol)

            def _fetch():
                df = pro.daily_basic(ts_code=ts_code, limit=1)
                if df is None or df.empty:
                    return None
                row = df.iloc[0]
                return {
                    "symbol": str(symbol).zfill(6),
                    "pe_ttm": self._safe_float(row.get("pe_ttm")),
                    "pb": self._safe_float(row.get("pb")),
                    "total_market_cap": self._safe_float(row.get("total_mv")),
                    "float_market_cap": self._safe_float(row.get("circ_mv")),
                    "turnover_rate": self._safe_float(row.get("turnover_rate")),
                    "source": self.name,
                }

            return await asyncio.to_thread(_fetch)
        except Exception as e:
            logger.debug("Tushare fundamentals failed for %s: %s", symbol, e)
            return None

    async def get_all_stock_quotes(self) -> Optional[list[dict]]:
        """获取全市场所有 A 股的实时行情数据（通过 Tushare）。

        Uses pro.daily for latest trading day and pro.stock_basic for names.
        """
        pro = self._get_client()
        if pro is None:
            return None
        try:

            def _fetch():
                # Get stock list first for names
                stock_list_df = pro.stock_basic(
                    exchange="", list_status="L", fields="ts_code,symbol,name,market"
                )
                if stock_list_df is None or stock_list_df.empty:
                    return None

                # Create name map
                name_map = {}
                for _, row in stock_list_df.iterrows():
                    code = str(row.get("symbol", "")).zfill(6)
                    name_map[code] = str(row.get("name", ""))

                # Get latest daily quotes
                # Use trade_calendar to get latest trade date if needed
                # For now, just get last 1 day of data
                daily_df = pro.daily(trade_date="", limit=5000)
                if daily_df is None or daily_df.empty:
                    # Fallback: get each stock individually (slow)
                    logger.info("Tushare bulk daily fetch failed, trying by list")
                    return None

                all_stocks = []
                seen_symbols = set()

                for _, row in daily_df.iterrows():
                    ts_code = str(row.get("ts_code", ""))
                    if "." in ts_code:
                        symbol = ts_code.split(".")[0].zfill(6)
                    else:
                        symbol = ts_code.zfill(6)

                    if not symbol or symbol in seen_symbols:
                        continue
                    seen_symbols.add(symbol)

                    market = "sh" if symbol.startswith("6") else "sz"
                    if symbol.startswith(("8", "4")):
                        market = "bj"

                    close = self._safe_float(row.get("close"))
                    pre_close = self._safe_float(row.get("pre_close"))
                    pct_chg = self._safe_float(row.get("pct_chg"))
                    up_limit = None
                    down_limit = None
                    if pre_close:
                        up_limit = round(pre_close * 1.1, 2)
                        down_limit = round(pre_close * 0.9, 2)
                        # Handle ST stocks
                        if "ST" in name_map.get(symbol, ""):
                            up_limit = round(pre_close * 1.05, 2)
                            down_limit = round(pre_close * 0.95, 2)

                    is_limit_up = False
                    is_limit_down = False
                    if close and up_limit and close >= up_limit - 0.001:
                        is_limit_up = True
                    elif close and down_limit and close <= down_limit + 0.001:
                        is_limit_down = True

                    all_stocks.append({
                        "symbol": symbol,
                        "name": name_map.get(symbol, ""),
                        "market": market,
                        "price": close or 0.0,
                        "change_pct": pct_chg or 0.0,
                        "change_amount": self._safe_float(row.get("change")),
                        "volume": self._safe_int(row.get("vol")),
                        "turnover": self._safe_float(row.get("amount")),
                        "high": self._safe_float(row.get("high")),
                        "low": self._safe_float(row.get("low")),
                        "open": self._safe_float(row.get("open")),
                        "prev_close": pre_close,
                        "turnover_rate": None,  # Not in basic daily
                        "pe_ratio": None,
                        "amplitude": self._safe_float(row.get("high")) - self._safe_float(row.get("low")) if row.get("high") and row.get("low") else None,
                        "total_market_cap": None,
                        "float_market_cap": None,
                        "limit_up_price": up_limit,
                        "limit_down_price": down_limit,
                        "is_limit_up": is_limit_up,
                        "is_limit_down": is_limit_down,
                        "board": "sh_main" if symbol.startswith("6") else "sz_main",
                    })

                return all_stocks if all_stocks else None

            result = await asyncio.to_thread(_fetch)
            if result:
                logger.info("Tushare all-stock quotes: collected %d stocks", len(result))
            return result
        except Exception as e:
            logger.warning("Tushare all-stock quotes failed: %s", e)
            return None

    async def get_limit_up_stocks(
        self, trade_date: str = "", market: str = "all"
    ) -> Optional[list[dict]]:
        """获取涨停股票数据（通过 Tushare limit_list_d）。"""
        pro = self._get_client()
        if pro is None:
            return None
        try:
            ts_date = trade_date.replace("-", "") if trade_date else ""

            def _fetch():
                df = pro.limit_list_d(trade_date=ts_date, limit_type="U")
                if df is None or df.empty:
                    return None

                items = []
                for _, row in df.iterrows():
                    ts_code = str(row.get("ts_code", ""))
                    if "." in ts_code:
                        symbol = ts_code.split(".")[0].zfill(6)
                    else:
                        symbol = ts_code.zfill(6)

                    if not symbol or symbol == "000000":
                        continue

                    market_code = "sh" if symbol.startswith("6") else "sz"
                    if market != "all" and market_code != market:
                        continue

                    items.append({
                        "symbol": symbol,
                        "name": str(row.get("name", "")),
                        "market": market_code,
                        "trade_date": trade_date,
                        "price": self._safe_float(row.get("close")),
                        "change_pct": self._safe_float(row.get("pct_chg")),
                        "volume": None,
                        "turnover": self._safe_float(row.get("fd_amount")),
                        "turnover_rate": self._safe_float(row.get("fl_ratio")),
                        "first_limit_up_time": str(row.get("first_time", "")) or None,
                        "last_limit_up_time": str(row.get("last_time", "")) or None,
                        "seal_amount": self._safe_float(row.get("fd_amount")),
                        "consecutive_days": self._safe_int(row.get("open_times")),
                        "reason": "",
                        "source": self.name,
                    })
                return items if items else None

            return await asyncio.to_thread(_fetch)
        except Exception as e:
            logger.debug("Tushare limit-up stocks failed: %s", e)
            return None
