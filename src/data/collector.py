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
from src.data.sources.tushare_source import TushareSource
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
    "tushare",
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
            "tushare": TushareSource(settings),
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

    @staticmethod
    def _infer_market(symbol: str) -> str:
        """根据股票代码推断所属市场。

        规则（A 股六位数代码）：
        - ``6`` 开头 → 上海交易所（sh），含主板/科创板
        - ``0`` 或 ``3`` 开头 → 深圳交易所（sz），含主板/中小板/创业板
        - ``4`` / ``8`` / ``9`` 开头 → 北京交易所（bj），含北交所股票
        - 其他 → 默认 ``"sz"``

        >>> DataCollector._infer_market("600519")
        'sh'
        >>> DataCollector._infer_market("000001")
        'sz'
        >>> DataCollector._infer_market("830799")
        'bj'
        """
        code = str(symbol or "").strip().zfill(6)
        if code.startswith("6"):
            return "sh"
        if code.startswith(("0", "3")):
            return "sz"
        if code.startswith(("4", "8", "9")):
            return "bj"
        return "sz"

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

        # 按优先级尝试数据源
        priority = self._domestic_priority("market_list", self._priority.get("market_list", []))
        if not priority:
            priority = ["eastmoney", "tushare"]

        rows = None
        last_error = ""
        for source_name in priority:
            source = self._sources.get(source_name)
            if not source:
                continue
            try:
                method = getattr(source, "get_all_stock_quotes", None)
                if not method:
                    continue
                rows = await method()
                if rows is not None and len(rows) > 0:
                    logger.info("获取全市场股票行情成功: %s (%d stocks)", source_name, len(rows))
                    break
            except Exception as e:
                last_error = str(e)
                logger.warning("获取全市场股票行情失败 (%s): %s", source_name, e)

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
            symbol = str(stock.get("symbol", ""))
            # 过滤创业板股票（300、301开头）
            if symbol.startswith(("300", "301")):
                continue
            # 市场筛选
            inferred_market = self._infer_market(symbol)
            if market == "sh" and inferred_market != "sh":
                continue
            if market == "sz" and inferred_market != "sz":
                continue
            if market == "bj" and inferred_market != "bj":
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
        """从全市场股票列表中筛选涨幅超过9.98%的股票。

        Returns:
            (rows, error_msg). error_msg is empty on success.
        """
        import os
        limit_up_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "limit_up")
        os.makedirs(limit_up_dir, exist_ok=True)

        # 0. 优先读取本地文件缓存
        if trade_date:
            local_data = self._read_limit_up_from_file(trade_date, limit_up_dir)
            if local_data:
                logger.info("读取本地涨停池数据: %d stocks for %s", len(local_data), trade_date)
                return self._filter_mainboard_limit_up(local_data, market), ""

        # 1. 从全市场股票列表中筛选涨幅 >=9.98% 的股票
        rows, err = await self.get_limit_up_from_market_list(
            trade_date=trade_date,
            market=market,
            min_change_pct=9.98
        )

        if rows is not None and len(rows) > 0:
            if trade_date:
                self._write_limit_up_to_file(trade_date, rows, limit_up_dir)
            logger.info("从全市场数据筛选出 %d 只涨停股 (阈值 9.98%%)", len(rows))
            return rows, ""

        # 筛选失败
        return [], err or "无法从全市场数据筛选涨停股"

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
                    "market": self._infer_market(code),
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

    # ---- Chanlun (缠论) Buy Signals ----

    async def _detect_chanlun_signals_for_stock(
        self, stock: dict, kline: list[dict]
    ) -> list[dict]:
        """检测单只股票的缠论买入信号。"""
        signals = []
        if not kline or len(kline) < 30:
            return signals

        symbol = stock.get("symbol", "")
        name = stock.get("name", "")
        market = stock.get("market", self._infer_market(symbol))
        trade_date = stock.get("trade_date", datetime.now().strftime("%Y-%m-%d"))

        df = pd.DataFrame(kline)
        if len(df) < 30:
            return signals

        # 确保数据按日期升序排列
        df = df.sort_values("date").reset_index(drop=True)

        # 计算基本技术指标
        close_prices = df["close"].values
        high_prices = df["high"].values
        low_prices = df["low"].values
        volumes = df["volume"].values

        # 计算MACD
        exp12 = df["close"].ewm(span=12, adjust=False).mean()
        exp26 = df["close"].ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal

        # 计算KDJ
        low_min = df["low"].rolling(window=9).min()
        high_max = df["high"].rolling(window=9).max()
        rsv = (df["close"] - low_min) / (high_max - low_min) * 100
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d

        # 计算RSI
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        # 检测一买：下跌趋势背驰
        # 简化版：检测近期低点抬高，且MACD底背离
        if len(df) >= 60:
            recent_df = df.tail(60).copy()
            half_idx = len(recent_df) // 2
            first_half = recent_df.iloc[:half_idx]
            second_half = recent_df.iloc[half_idx:]

            first_low = first_half["low"].min()
            second_low = second_half["low"].min()
            # 使用 recent_df 对齐后的 MACD 切片（len(recent_df)==60），
            # 避免 macd.iloc[-60:-30] 与 recent_df.iloc[:30] 因全量/局部长度不一致导致错位
            recent_macd = macd.tail(len(recent_df)) if len(macd) >= len(recent_df) else macd
            first_macd_low = recent_macd.iloc[:half_idx].min() if len(recent_macd) >= half_idx else None
            second_macd_low = recent_macd.iloc[half_idx:].min() if len(recent_macd) > half_idx else None

            # 底背离条件：价格创新低但MACD不创新低
            if (first_low is not None and second_low is not None and
                first_macd_low is not None and second_macd_low is not None and
                second_low < first_low and second_macd_low > first_macd_low):
                # 一买信号
                signals.append({
                    "symbol": symbol,
                    "name": name,
                    "market": market,
                    "trade_date": trade_date,
                    "signal_type": "type1",
                    "signal_type_label": "一买",
                    "price": stock.get("price"),
                    "change_pct": stock.get("change_pct"),
                    "volume": stock.get("volume"),
                    "turnover": stock.get("turnover"),
                    "turnover_rate": stock.get("turnover_rate"),
                    "pivot_level": "30F",
                    "recent_pivot_high": float(recent_df["high"].max()),
                    "recent_pivot_low": float(second_low),
                    "divergence_type": "MACD底背离",
                    "macd_divergence": True,
                    "kdj_divergence": bool(k.iloc[-1] < 30),
                    "rsi_divergence": bool(rsi.iloc[-1] < 30),
                    "description": f"{name}({symbol}) 出现一买信号，MACD底背离",
                    "confidence_score": 0.7,
                })

        # 检测二买：回调不创新低
        # 简化版：近期有过一波上涨，回调低点高于前低
        if len(df) >= 40:
            recent_df = df.tail(40).copy()
            # 检测是否有上涨趋势
            mid_idx = len(recent_df) // 2
            early_low = recent_df.iloc[:mid_idx]["low"].min()
            later_low = recent_df.iloc[mid_idx:]["low"].min()
            early_high = recent_df.iloc[:mid_idx]["high"].max()
            later_high = recent_df.iloc[mid_idx:]["high"].max()

            if (later_low > early_low and later_high > early_high and
                k.iloc[-1] > d.iloc[-1] and k.iloc[-1] < 50):
                signals.append({
                    "symbol": symbol,
                    "name": name,
                    "market": market,
                    "trade_date": trade_date,
                    "signal_type": "type2",
                    "signal_type_label": "二买",
                    "price": stock.get("price"),
                    "change_pct": stock.get("change_pct"),
                    "volume": stock.get("volume"),
                    "turnover": stock.get("turnover"),
                    "turnover_rate": stock.get("turnover_rate"),
                    "pivot_level": "5F",
                    "recent_pivot_high": float(later_high),
                    "recent_pivot_low": float(later_low),
                    "divergence_type": "趋势确认",
                    "macd_divergence": bool(histogram.iloc[-1] > 0),
                    "kdj_divergence": bool(k.iloc[-1] > d.iloc[-1]),
                    "rsi_divergence": bool(40 < rsi.iloc[-1] < 60),
                    "description": f"{name}({symbol}) 出现二买信号，回调确认",
                    "confidence_score": 0.65,
                })

        # 检测三买：突破回抽
        # 简化版：价格突破近期高点后回踩确认
        if len(df) >= 30:
            recent_df = df.tail(30).copy()
            pivot_high = recent_df.iloc[:-5]["high"].max()
            current_price = close_prices[-1]
            current_low = low_prices[-1]
            prev_high = high_prices[-5:].max()

            # 突破后回踩
            if (pivot_high is not None and
                current_price > pivot_high * 0.98 and
                current_low > pivot_high * 0.95 and
                prev_high > pivot_high):
                signals.append({
                    "symbol": symbol,
                    "name": name,
                    "market": market,
                    "trade_date": trade_date,
                    "signal_type": "type3",
                    "signal_type_label": "三买",
                    "price": stock.get("price"),
                    "change_pct": stock.get("change_pct"),
                    "volume": stock.get("volume"),
                    "turnover": stock.get("turnover"),
                    "turnover_rate": stock.get("turnover_rate"),
                    "pivot_level": "30F",
                    "recent_pivot_high": float(pivot_high),
                    "recent_pivot_low": float(current_low),
                    "divergence_type": "突破回抽",
                    "macd_divergence": bool(macd.iloc[-1] > 0),
                    "kdj_divergence": bool(k.iloc[-1] > 50),
                    "rsi_divergence": bool(rsi.iloc[-1] > 50),
                    "description": f"{name}({symbol}) 出现三买信号，突破回抽确认",
                    "confidence_score": 0.75,
                })

        return signals

    async def get_chanlun_buy_signals(
        self, trade_date: str = "", market: str = "all", signal_type: str = "all"
    ) -> tuple[Optional[list[dict]], str]:
        """获取缠论买入信号股票列表。

        Args:
            trade_date: 交易日（YYYY-MM-DD），默认今日
            market: 市场筛选 ('all' | 'sh' | 'sz')
            signal_type: 信号类型 ('all' | 'type1' | 'type2' | 'type3')

        Returns:
            (list of signal dicts, error_msg)
        """
        effective_date = trade_date or datetime.now().strftime("%Y-%m-%d")

        # 获取全市场股票数据
        rows, err = await self.get_market_list(trade_date=trade_date)
        if rows is None:
            return [], err or "无法获取全市场数据"

        all_signals = []

        # 筛选符合基本条件的股票
        candidate_stocks = []
        for stock in rows:
            symbol = str(stock.get("symbol", ""))
            # 过滤创业板股票（300、301开头）
            if symbol.startswith(("300", "301")):
                continue
            # 市场筛选
            inferred_market = self._infer_market(symbol)
            if market == "sh" and inferred_market != "sh":
                continue
            if market == "sz" and inferred_market != "sz":
                continue
            if market == "bj" and inferred_market != "bj":
                continue
            # 确保有基本数据
            if not stock.get("price") or float(stock.get("price", 0)) <= 0:
                continue
            # 添加市场标识
            stock["market"] = inferred_market
            stock["trade_date"] = effective_date
            candidate_stocks.append(stock)

        # 限制检测数量以提高性能（优先选择成交量大的股票）
        candidate_stocks.sort(
            key=lambda x: float(x.get("turnover") or 0),
            reverse=True
        )
        candidate_stocks = candidate_stocks[:200]  # 先检查前200只

        logger.info("开始检测 %d 只股票的缠论信号...", len(candidate_stocks))

        # 逐个检测信号
        import asyncio
        semaphore = asyncio.Semaphore(10)  # 并发限制

        async def _process_stock(stock):
            async with semaphore:
                try:
                    symbol = stock.get("symbol", "")
                    kline = await self.get_kline(symbol, limit=120)
                    signals = await self._detect_chanlun_signals_for_stock(stock, kline)
                    return signals
                except Exception as e:
                    logger.debug("检测 %s 缠论信号失败: %s", stock.get("symbol"), e)
                    return []

        # 并发处理
        tasks = [_process_stock(stock) for stock in candidate_stocks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 收集结果
        for result in results:
            if isinstance(result, list):
                all_signals.extend(result)

        # 按信号类型筛选
        if signal_type != "all":
            all_signals = [s for s in all_signals if s.get("signal_type") == signal_type]

        # 按置信度排序
        all_signals.sort(
            key=lambda x: float(x.get("confidence_score", 0)),
            reverse=True
        )

        logger.info("检测完成，共发现 %d 个缠论买入信号", len(all_signals))
        return all_signals, ""

