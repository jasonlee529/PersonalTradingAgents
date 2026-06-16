import logging
from datetime import datetime
from typing import Optional

import pandas as pd

from src.config import Settings
from src.data.cache import DataCache
from src.data.historical_store import HistoricalDataStore
from src.data.sources.baostock_source import BaoStockSource
from src.data.sources.baidu_source import BaiduSource
from src.data.sources.cls_source import CLSSource
from src.data.sources.cninfo_source import CninfoSource
from src.data.sources.eastmoney_source import EastmoneySource
from src.data.sources.indicator_source import IndicatorSource
from src.data.sources.sina_source import SinaSource
from src.data.sources.tencent_source import TencentSource
from src.data.sources.tdx_source import TdxSource
from src.data.sources.ths_source import THSSource
from src.data.sources.xueqiu_source import XueqiuSource
from src.utils.ticker import detect_market

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 260
DEFAULT_KLINE_LIMIT = TRADING_DAYS_PER_YEAR * 2


DOMESTIC_SOURCE_NAMES = {
    "tencent",
    "sina",
    "eastmoney",
    "ths",
    "tdx",
    "baidu",
    "cls",
    "cninfo",
    "baostock",
    "indicator",
    "xueqiu",
}


class DataCollector:
    """Unified data collector with caching and config-driven source fallback."""

    def __init__(self, settings: Settings, cache: DataCache):
        self.settings = settings
        self.cache = cache
        self._sources = {
            "tencent": TencentSource(),
            "sina": SinaSource(),
            "eastmoney": EastmoneySource(),
            "ths": THSSource(),
            "tdx": TdxSource(),
            "baidu": BaiduSource(),
            "cls": CLSSource(),
            "cninfo": CninfoSource(),
            "baostock": BaoStockSource(),
            "indicator": IndicatorSource(settings),
            "xueqiu": XueqiuSource(settings),
        }
        self._priority = getattr(settings, "data_source_priority", {})
        self._historical_store = None
        if getattr(settings, "local_history_enabled", False):
            self._historical_store = HistoricalDataStore(settings)

    def _cache_key(self, data_type: str, symbol: str = "", **kwargs) -> str:
        parts = [data_type]
        if symbol:
            parts.append(detect_market(symbol))
            parts.append(symbol)
        for k, v in sorted(kwargs.items()):
            parts.append(f"{k}={v}")
        return ":".join(parts)

    async def _fetch_with_fallback(
        self, data_type: str, method_name: str, symbol: str = "", **kwargs
    ):
        """Fetch data by trying sources in priority order (first success wins)."""
        key = self._cache_key(data_type, symbol, **kwargs)
        cached = await self.cache.get(key)
        if cached:
            return cached

        priority = self._domestic_priority(data_type, self._priority.get(data_type, []))
        if not priority:
            if data_type == "quote":
                priority = ["tencent", "eastmoney", "sina", "baostock"]
            elif data_type == "kline":
                priority = ["sina", "eastmoney", "tencent", "baostock"]
            elif data_type == "fundamentals":
                priority = ["tencent", "eastmoney", "sina"]
            elif data_type == "announcements":
                priority = ["ths", "cninfo"]
            elif data_type == "research_reports":
                priority = ["eastmoney"]
            elif data_type == "limit_up_stocks":
                priority = ["eastmoney", "tdx", "sina", "tushare"]
            else:
                priority = []

        result = None
        for source_name in priority:
            source = self._sources.get(source_name)
            if not source:
                continue
            try:
                method = getattr(source, method_name)
                if symbol:
                    result = await method(symbol, **kwargs)
                else:
                    result = await method(**kwargs)
                if result is not None:
                    logger.debug("%s.%s succeeded via %s", data_type, method_name, source_name)
                    break
            except Exception as e:
                logger.debug("%s.%s failed on %s: %s", data_type, method_name, source_name, e)

        if result:
            ttl_map = {
                "quote": self.settings.cache_ttl_quotes,
                "kline": self.settings.cache_ttl_kline,
                "fundamentals": self.settings.cache_ttl_fundamentals,
                "news": self.settings.cache_ttl_news,
                "global_news": self.settings.cache_ttl_news,
                "indicators": self.settings.cache_ttl_indicators,
                "announcements": self.settings.cache_ttl_announcements,
                "research_reports": self.settings.cache_ttl_research_reports,
                "limit_up_stocks": self.settings.cache_ttl_quotes,
            }
            ttl = ttl_map.get(data_type, 3600)
            await self.cache.set(key, result, ttl=ttl)
        return result

    async def _fetch_and_merge(
        self, data_type: str, method_name: str, symbol: str = "", merge_fn=None, **kwargs
    ):
        """Fetch data from ALL sources in priority order and merge results."""
        key = self._cache_key(data_type, symbol, **kwargs)
        cached = await self.cache.get(key)
        if cached:
            return cached

        priority = self._domestic_priority(data_type, self._priority.get(data_type, []))

        results = []
        for source_name in priority:
            source = self._sources.get(source_name)
            if not source:
                continue
            try:
                method = getattr(source, method_name)
                if symbol:
                    result = await method(symbol, **kwargs)
                else:
                    result = await method(**kwargs)
                if result is not None:
                    results.append(result)
                    logger.debug("%s.%s collected from %s", data_type, method_name, source_name)
            except Exception as e:
                logger.debug("%s.%s failed on %s: %s", data_type, method_name, source_name, e)

        merged = merge_fn(results) if merge_fn and results else (results[0] if results else None)

        if merged:
            ttl_map = {
                "quote": self.settings.cache_ttl_quotes,
                "kline": self.settings.cache_ttl_kline,
                "fundamentals": self.settings.cache_ttl_fundamentals,
                "news": self.settings.cache_ttl_news,
                "global_news": self.settings.cache_ttl_news,
                "indicators": self.settings.cache_ttl_indicators,
                "announcements": self.settings.cache_ttl_announcements,
                "research_reports": self.settings.cache_ttl_research_reports,
                "limit_up_stocks": self.settings.cache_ttl_quotes,
            }
            ttl = ttl_map.get(data_type, 3600)
            await self.cache.set(key, merged, ttl=ttl)
        return merged

    @staticmethod
    def _merge_news(results: list[list[dict]]) -> list[dict]:
        """Merge and deduplicate news articles from multiple sources."""
        if not results:
            return []
        seen = set()
        merged = []
        for articles in results:
            for article in articles:
                title = article.get("title", "").strip().lower()
                if title and title not in seen:
                    seen.add(title)
                    merged.append(article)
        # Sort by time descending (most recent first)
        merged.sort(key=lambda x: x.get("time", ""), reverse=True)
        return merged

    @staticmethod
    def _domestic_priority(data_type: str, priority: list[str]) -> list[str]:
        blocked = [source for source in priority if source not in DOMESTIC_SOURCE_NAMES]
        if blocked:
            raise RuntimeError(
                f"Unsupported or foreign data source configured for '{data_type}': {blocked}"
            )
        return priority

    @staticmethod
    def _merge_fundamentals(results: list[dict]) -> dict:
        """Merge fundamentals dicts from multiple sources, preserving all fields."""
        if not results:
            return {}
        merged = dict(results[0])
        sources = [merged.pop("source", "")]
        for result in results[1:]:
            src = result.pop("source", "")
            if src:
                sources.append(src)
            for k, v in result.items():
                if k not in merged or (not merged[k] and v):
                    merged[k] = v
        merged["sources"] = sources
        return merged

    @staticmethod
    def _merge_kline_by_date(local: list[dict], remote: list[dict]) -> list[dict]:
        """Merge local and remote kline data, remote overrides local for same date."""
        if not local:
            return remote
        if not remote:
            return local
        by_date = {r["date"]: r for r in local}
        for r in remote:
            by_date[r["date"]] = r
        return sorted(by_date.values(), key=lambda x: x["date"])

    @staticmethod
    def _mainboard_market(symbol: str) -> str | None:
        code = str(symbol or "").strip().zfill(6)
        if len(code) != 6 or not code.isdigit():
            return None
        if code.startswith("60"):
            return "sh"
        if code.startswith("00"):
            return "sz"
        return None

    @classmethod
    def _filter_mainboard_limit_up(cls, rows: list[dict], market: str = "all") -> list[dict]:
        market = (market or "all").lower()
        results = []
        for row in rows or []:
            item = dict(row)
            board_market = cls._mainboard_market(str(item.get("symbol", "")))
            if board_market is None:
                continue
            if market in {"sh", "sse", "sh_main"} and board_market != "sh":
                continue
            if market in {"sz", "szse", "sz_main"} and board_market != "sz":
                continue
            item["market"] = board_market
            results.append(item)
        return results

    # ---- Core data ----
    @staticmethod
    def _quote_needs_enrichment(quote: dict) -> bool:
        return (
            not quote.get("name")
            or not quote.get("price")
            or (not quote.get("volume") and not quote.get("turnover"))
        )

    @staticmethod
    def _merge_quote(base: dict | None, extra: dict) -> dict:
        merged = dict(base or {})
        sources: list[str] = []
        for source in (merged.get("source"), extra.get("source")):
            if not source:
                continue
            sources.extend(str(source).split("+"))

        def is_blank(value) -> bool:
            return value is None or value == "" or value == "-"

        def can_replace(value) -> bool:
            return is_blank(value) or value == 0 or value == 0.0

        for key, value in extra.items():
            if key == "source" or is_blank(value):
                continue
            if key not in merged or (can_replace(merged.get(key)) and not can_replace(value)):
                merged[key] = value

        if sources:
            merged["source"] = "+".join(dict.fromkeys(sources))
        return merged

    async def get_quote(self, symbol: str) -> Optional[dict]:
        key = self._cache_key("quote", symbol)
        cached = await self.cache.get(key)
        if cached and not self._quote_needs_enrichment(cached):
            return cached

        priority = self._domestic_priority("quote", self._priority.get("quote", []))
        if not priority:
            priority = ["tencent", "eastmoney", "sina", "baostock"]

        merged = dict(cached or {})
        for source_name in priority:
            source = self._sources.get(source_name)
            if not source:
                continue
            try:
                result = await source.get_quote(symbol)
                if result is None:
                    continue
                merged = self._merge_quote(merged, result)
                logger.debug("quote.get_quote collected from %s", source_name)
                if not self._quote_needs_enrichment(merged):
                    break
            except Exception as e:
                logger.debug("quote.get_quote failed on %s: %s", source_name, e)

        if merged:
            await self.cache.set(key, merged, ttl=self.settings.cache_ttl_quotes)
            return merged
        return None

    async def get_kline(
        self, symbol: str, period: str = "1d", limit: int = DEFAULT_KLINE_LIMIT
    ) -> Optional[list[dict]]:
        # Local-first: check persistent store before API/cache
        local = None
        if getattr(self.settings, "local_history_enabled", False) and self._historical_store is not None:
            local = await self._historical_store.load_kline(symbol, period)
            if local:
                last_date = local[-1].get("date", "")
                today = datetime.now().strftime("%Y-%m-%d")
                if last_date == today and len(local) >= limit:
                    return local[-limit:]

        result = await self._fetch_with_fallback("kline", "get_kline", symbol, period=period, limit=limit)

        if local and result:
            merged = self._merge_kline_by_date(local, result)
            if getattr(self.settings, "local_history_enabled", False) and self._historical_store is not None:
                await self._historical_store.save_kline(symbol, period, merged)
            return merged[-limit:]

        if result and getattr(self.settings, "local_history_enabled", False) and self._historical_store is not None:
            await self._historical_store.save_kline(symbol, period, result)

        return result[-limit:] if result else (local[-limit:] if local else None)

    async def get_fundamentals(self, symbol: str) -> Optional[dict]:
        return await self._fetch_and_merge(
            "fundamentals", "get_fundamentals", symbol, merge_fn=self._merge_fundamentals
        )

    # ---- Financial statements ----
    async def get_balance_sheet(self, symbol: str, freq: str = "quarterly") -> Optional[list[dict]]:
        return await self._fetch_with_fallback("balance_sheet", "get_balance_sheet", symbol, freq=freq)

    async def get_cashflow(self, symbol: str, freq: str = "quarterly") -> Optional[list[dict]]:
        return await self._fetch_with_fallback("cashflow", "get_cashflow", symbol, freq=freq)

    async def get_income_statement(self, symbol: str, freq: str = "quarterly") -> Optional[list[dict]]:
        return await self._fetch_with_fallback("income_statement", "get_income_statement", symbol, freq=freq)

    # ---- News ----
    async def get_news(self, symbol: str, start_date: str = "", end_date: str = "", limit: int = 20) -> Optional[list[dict]]:
        merged = await self._fetch_and_merge(
            "news", "get_news", symbol,
            merge_fn=lambda rs: self._merge_news(rs)[:limit],
            start_date=start_date, end_date=end_date, limit=limit,
        )
        return merged

    async def get_global_news(self, look_back_days: int = 7, limit: int = 10) -> Optional[list[dict]]:
        merged = await self._fetch_and_merge(
            "global_news", "get_global_news",
            merge_fn=lambda rs: self._merge_news(rs)[:limit],
            look_back_days=look_back_days, limit=limit,
        )
        return merged

    # ---- Signals ----
    async def fetch_consensus_expectations(self, symbol: str) -> Optional[dict]:
        return await self._fetch_with_fallback("consensus_expectations", "fetch_consensus_expectations", symbol)

    async def fetch_market_heatmap(self, date: str = "") -> Optional[list[dict]]:
        return await self._fetch_with_fallback("market_heatmap", "fetch_market_heatmap", date=date)

    async def fetch_cross_border_flow(self, include_history: bool = False) -> Optional[dict]:
        return await self._fetch_with_fallback("cross_border_flow", "fetch_cross_border_flow", include_history=include_history)

    async def fetch_theme_exposure(self, symbol: str) -> Optional[list[dict]]:
        return await self._fetch_with_fallback("theme_exposure", "fetch_theme_exposure", symbol)

    async def fetch_order_flow_profile(self, symbol: str, include_history: bool = True) -> Optional[dict]:
        return await self._fetch_with_fallback("order_flow_profile", "fetch_order_flow_profile", symbol, include_history=include_history)

    async def fetch_trading_seat_activity(self, symbol: str, trade_date: str = "", look_back_days: int = 30) -> Optional[dict]:
        return await self._fetch_with_fallback("trading_seat_activity", "fetch_trading_seat_activity", symbol, trade_date=trade_date, look_back_days=look_back_days)

    async def fetch_supply_unlock_schedule(self, symbol: str, trade_date: str = "", forward_days: int = 90) -> Optional[list[dict]]:
        return await self._fetch_with_fallback("supply_unlock_schedule", "fetch_supply_unlock_schedule", symbol, trade_date=trade_date, forward_days=forward_days)

    async def fetch_peer_industry_snapshot(self, symbol: str, top_n: int = 20) -> Optional[list[dict]]:
        return await self._fetch_with_fallback("peer_industry_snapshot", "fetch_peer_industry_snapshot", symbol, top_n=top_n)

    async def list_concept_boards(self, limit: int = 100) -> Optional[list[dict]]:
        return await self._fetch_with_fallback("concept_boards", "list_concept_boards", limit=limit)

    async def list_industry_boards(self, limit: int = 100) -> Optional[list[dict]]:
        return await self._fetch_with_fallback("industry_boards", "list_industry_boards", limit=limit)

    async def get_board_stocks(self, board_code: str, limit: int = 100) -> Optional[list[dict]]:
        return await self._fetch_with_fallback("board_stocks", "get_board_stocks", board_code, limit=limit)

    async def get_announcements(
        self, symbol: str, start_date: str = "", end_date: str = "", category: str = "", limit: int = 30
    ) -> Optional[list[dict]]:
        """Fetch stock announcements from Tonghuashun, falling back to Cninfo."""
        return await self._fetch_with_fallback(
            "announcements", "get_announcements", symbol,
            start_date=start_date, end_date=end_date, category=category, limit=limit,
        )

    # ---- Market overview ----
    async def get_market_indices(self) -> Optional[list[dict]]:
        return await self._fetch_with_fallback("market_indices", "get_market_indices")

    async def get_market_statistics(self) -> Optional[dict]:
        return await self._fetch_with_fallback("market_statistics", "get_market_statistics")

    def _market_list_file_path(self, trade_date: str) -> str:
        import os
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "market_list",
        )
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, f"market_list_{trade_date}.json")

    def _read_market_list_from_file(self, trade_date: str) -> Optional[list[dict]]:
        import json
        filepath = self._market_list_file_path(trade_date)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("读取本地全市场数据: %d stocks for %s", len(data), trade_date)
            return data
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning("读取本地全市场数据失败 %s: %s", filepath, e)
            return None

    def _write_market_list_to_file(self, trade_date: str, data: list[dict]) -> None:
        import json
        filepath = self._market_list_file_path(trade_date)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("已保存全市场数据到本地: %s (%d stocks)", filepath, len(data))
        except Exception as e:
            logger.warning("保存全市场数据失败 %s: %s", filepath, e)

    async def get_market_list(
        self, trade_date: str = "", refresh: bool = False
    ) -> tuple[Optional[list[dict]], str]:
        """获取全市场股票列表及行情数据。

        Returns:
            (list of stock dicts, error_msg)
        """
        effective_date = trade_date or datetime.now().strftime("%Y-%m-%d")

        if not refresh:
            local_data = self._read_market_list_from_file(effective_date)
            if local_data:
                return local_data, ""

        eastmoney = self._sources.get("eastmoney")
        if eastmoney is None:
            return None, "eastmoney 数据源未初始化"

        rows = await eastmoney.get_all_stock_quotes()
        if rows is None or len(rows) == 0:
            return None, "无法获取全市场股票行情"

        for row in rows:
            row.setdefault("trade_date", effective_date)

        self._write_market_list_to_file(effective_date, rows)
        return rows, ""

    async def get_limit_up_from_market_list(
        self, trade_date: str = "", market: str = "all", min_change_pct: Optional[float] = 9.5
    ) -> tuple[Optional[list[dict]], str]:
        """从全市场行情数据中筛选出涨停股票。

        Args:
            trade_date: 交易日（YYYY-MM-DD），默认今日
            market: 市场筛选 ('all' | 'sh' | 'sz')
            min_change_pct: 最小涨跌幅阈值，默认 9.5%

        Returns:
            (list of limit-up stock dicts, error_msg)
        """
        rows, err = await self.get_market_list(trade_date=trade_date)
        if rows is None:
            return None, err or "全市场数据不可用"

        effective_date = trade_date or datetime.now().strftime("%Y-%m-%d")
        filtered = []
        for stock in rows:
            # 市场筛选
            if market == "sh" and not str(stock.get("symbol", "")).startswith("6"):
                continue
            if market == "sz" and not str(stock.get("symbol", "")).startswith(("0", "3")):
                continue

            # 涨停判定：is_limit_up=True 或涨跌幅 >= 阈值
            is_up = bool(stock.get("is_limit_up"))
            if not is_up:
                change_pct = float(stock.get("change_pct") or 0)
                if min_change_pct is not None and change_pct >= min_change_pct:
                    is_up = True

            if is_up:
                filtered.append({
                    "symbol": stock.get("symbol", ""),
                    "name": stock.get("name", ""),
                    "market": stock.get("market", ""),
                    "trade_date": effective_date,
                    "price": stock.get("price"),
                    "change_pct": stock.get("change_pct"),
                    "volume": stock.get("volume"),
                    "turnover": stock.get("turnover"),
                    "turnover_rate": stock.get("turnover_rate"),
                    "limit_up_price": stock.get("limit_up_price"),
                    "limit_down_price": stock.get("limit_down_price"),
                    "first_limit_up_time": None,
                    "last_limit_up_time": None,
                    "seal_amount": None,
                    "consecutive_days": None,
                    "reason": "",
                    "source": "market_list",
                })

        logger.info("从全市场数据筛选出 %d 只涨停股 (%s, 阈值 %s%%)",
                    len(filtered), effective_date, min_change_pct)
        return filtered, ""

    async def get_limit_up_stocks(
        self, trade_date: str = "", market: str = "all"
    ) -> tuple[Optional[list[dict]], str]:
        """Returns (rows, error_msg). error_msg is empty on success."""
        import os
        limit_up_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "limit_up")
        os.makedirs(limit_up_dir, exist_ok=True)

        # 0. 优先读取本地文件缓存
        if trade_date:
            local_data = self._read_limit_up_from_file(trade_date, limit_up_dir)
            if local_data:
                logger.info("读取本地涨停池数据: %d stocks for %s", len(local_data), trade_date)
                return self._filter_mainboard_limit_up(local_data, market), ""

        # 1. 按照配置优先级获取数据: eastmoney > tdx > sina > tushare
        errors = []
        for source_name in ["eastmoney", "tdx", "sina", "tushare"]:
            try:
                if source_name == "tushare":
                    rows, err = await self._fetch_limit_up_tushare(trade_date)
                    if rows is not None:
                        if trade_date:
                            self._write_limit_up_to_file(trade_date, rows, limit_up_dir)
                        return self._filter_mainboard_limit_up(rows, market), ""
                    if err:
                        errors.append(f"{source_name}: {err}")
                else:
                    source = self._sources.get(source_name)
                    if source:
                        rows = await source.get_limit_up_stocks(trade_date=trade_date, market=market)
                        if rows is not None and len(rows) > 0:
                            if trade_date:
                                self._write_limit_up_to_file(trade_date, rows, limit_up_dir)
                            return self._filter_mainboard_limit_up(rows, market), ""
                        errors.append(f"{source_name}: 无数据")
            except Exception as e:
                errors.append(f"{source_name}: {e}")
                logger.warning("get_limit_up_stocks failed for %s: %s", source_name, e)

        # 所有数据源都失败
        return [], "; ".join(errors) if errors else "数据源请求失败，无法获取涨停数据"

    @staticmethod
    def _read_limit_up_from_file(trade_date: str, data_dir: str) -> Optional[list[dict]]:
        import os
        import json
        filename = f"limit_up_{trade_date}.json"
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("读取本地涨停池文件失败 %s: %s", filepath, e)
        return None

    @staticmethod
    def _write_limit_up_to_file(trade_date: str, data: list[dict], data_dir: str) -> None:
        import os
        import json
        filename = f"limit_up_{trade_date}.json"
        filepath = os.path.join(data_dir, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug("写入本地涨停池文件: %s", filepath)
        except Exception as e:
            logger.warning("写入本地涨停池文件失败 %s: %s", filepath, e)

    async def _fetch_limit_up_tushare(
        self, trade_date: str
    ) -> tuple[Optional[list[dict]], str]:
        """通过 tushare Pro limit_list_d 获取涨停池数据。"""
        token = getattr(self.settings, "tushare_api_key", "")
        if not token:
            return None, "未配置 tushare_api_key"

        if not trade_date:
            from datetime import datetime
            trade_date = datetime.now().strftime("%Y-%m-%d")
        ts_date = trade_date.replace("-", "")

        try:
            import tushare as ts

            def _query():
                pro = ts.pro_api(token)
                df = pro.limit_list_d(trade_date=ts_date, limit_type="U")
                return df

            import asyncio
            df = await asyncio.to_thread(_query)

            if df is None or df.empty:
                return None, f"tushare 涨停池无 {trade_date} 数据"

            items: list[dict] = []
            for _, row in df.iterrows():
                code = str(row.get("ts_code", "")).split(".")[0].zfill(6)
                if not code or code == "000000":
                    continue
                items.append({
                    "symbol": code,
                    "name": str(row.get("name") or ""),
                    "market": "sh" if code.startswith("6") else "sz",
                    "trade_date": trade_date,
                    "price": self._safe_float(row.get("close")),
                    "change_pct": self._safe_float(row.get("pct_chg")),
                    "volume": None,
                    "turnover": self._safe_float(row.get("fd_amount")),
                    "turnover_rate": self._safe_float(row.get("fl_ratio")),
                    "first_limit_up_time": str(row.get("first_time") or "") or None,
                    "last_limit_up_time": str(row.get("last_time") or "") or None,
                    "seal_amount": self._safe_float(row.get("fd_amount")),
                    "consecutive_days": self._safe_int(row.get("open_times")),
                    "reason": "",
                    "source": "tushare",
                })
            logger.info("tushare limit-up pool: %d stocks for %s", len(items), trade_date)
            return items, ""
        except ImportError:
            return None, "tushare 未安装"
        except Exception as e:
            logger.warning("tushare limit_list_d failed for %s: %s", trade_date, e)
            return None, f"tushare 请求失败: {e}"

    @staticmethod
    def _safe_float(v) -> Optional[float]:
        try:
            f = float(v)
            return f if not (f != f) else None  # NaN check
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(v) -> Optional[int]:
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    async def get_sector_rankings(self, n: int = 5) -> Optional[tuple[list[dict], list[dict]]]:
        return await self._fetch_with_fallback("sector_rankings", "get_sector_rankings", n=n)

    async def get_research_reports(
        self, symbol: str, start_date: str = "", end_date: str = "", limit: int = 30
    ) -> Optional[list[dict]]:
        """Fetch stock research reports from Eastmoney."""
        return await self._fetch_with_fallback(
            "research_reports", "get_research_reports", symbol,
            start_date=start_date, end_date=end_date, limit=limit,
        )

    # ---- Indicators (derived from kline) ----
    async def get_indicators(self, symbol: str, period: str = "1d", indicator_list: list[str] = None) -> Optional[dict]:
        key = self._cache_key("indicators", symbol, period=period)
        cached = await self.cache.get(key)
        if cached:
            return cached

        kline = await self.get_kline(symbol, period=period, limit=120)
        if not kline:
            return None

        df = pd.DataFrame(kline)
        if not all(c in df.columns for c in ["open", "high", "low", "close", "volume"]):
            logger.warning("K-line data missing required columns for %s", symbol)
            return None

        result = self._sources["indicator"].compute(df, indicators=indicator_list)
        if result:
            await self.cache.set(key, result, ttl=self.settings.cache_ttl_indicators)
        return result

    # ---- Full snapshot ----
    async def get_full_snapshot(
        self, symbol: str, kline_limit: int = DEFAULT_KLINE_LIMIT
    ) -> dict:
        quote = await self.get_quote(symbol)
        kline = await self.get_kline(symbol, limit=kline_limit)
        fundamentals = await self.get_fundamentals(symbol)
        indicators = await self.get_indicators(symbol)
        return {
            "symbol": symbol,
            "quote": quote,
            "kline": kline,
            "fundamentals": fundamentals,
            "indicators": indicators,
            "timestamp": pd.Timestamp.now().isoformat(),
        }

