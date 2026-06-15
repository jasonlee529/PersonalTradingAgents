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
            if self._is_valid_data_result(data_type, cached):
                return cached
            logger.info("Ignoring invalid cached %s result for key=%s", data_type, key)
            await self.cache.delete(key)

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
            elif data_type == "market_indices":
                priority = ["eastmoney", "tencent", "sina"]
            elif data_type == "market_statistics":
                priority = ["eastmoney", "sina"]
            elif data_type == "sector_rankings":
                priority = ["eastmoney"]
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
                    if not self._is_valid_data_result(data_type, result):
                        logger.info(
                            "%s.%s via %s returned invalid data, trying next source",
                            data_type, method_name, source_name,
                        )
                        result = None
                        continue
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
            }
            ttl = ttl_map.get(data_type, 3600)
            await self.cache.set(key, result, ttl=ttl)
        return result

    @staticmethod
    def _is_valid_data_result(data_type: str, result) -> bool:
        if data_type == "market_statistics":
            if not isinstance(result, dict):
                return False
            breadth = sum(int(result.get(k) or 0) for k in ("up_count", "down_count", "flat_count"))
            return breadth >= 1000

        if data_type == "market_heatmap":
            if not isinstance(result, list):
                return False
            if not result:
                return True
            valid_rows = 0
            for item in result:
                if not isinstance(item, dict):
                    continue
                if not item.get("code") or not item.get("reason"):
                    continue
                if any(item.get(k) is not None for k in ("change_pct", "turnover", "amount", "dde_net")):
                    valid_rows += 1
            return valid_rows > 0 and valid_rows / max(len(result), 1) >= 0.8

        return True

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

