"""MarketHeatScanner — detect hot market concepts (signal source only).

No longer outputs StockSignal directly. Instead, extracts hot concepts
from limit-up stocks and fund flows, producing HotSignal[] that feeds
into ChainMapper for upstream expectation-gap discovery.

Input: THS hot stocks, Eastmoney fund flow, dragon-tiger board
Output: HotSignal[] (concept + heat_level + evidence + market_heatmap)
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from src.agents.sector_discovery.models import HotSignal
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector
from src.utils.trading_dates import get_recent_trade_dates

logger = logging.getLogger(__name__)

# Common concept keywords extracted from limit-up reasons
_CONCEPT_PATTERNS = [
    r"(.*?)概念",
    r"(.*?)板块",
    r"(.*?)产业链",
]

# Explicit concept mapping from hot stock reason text → canonical concept
_REASON_CONCEPT_MAP: dict[str, str] = {
    "固态电池": "固态电池",
    "半固态电池": "固态电池",
    "硫化物": "固态电池",
    "商业航天": "商业航天",
    "卫星": "商业航天",
    "火箭": "商业航天",
    "低空经济": "低空经济",
    "eVTOL": "低空经济",
    "无人机": "低空经济",
    "飞行器": "低空经济",
    "AI": "AI算力",
    "人工智能": "AI算力",
    "大模型": "AI算力",
    "算力": "AI算力",
    "光模块": "AI算力",
    "半导体": "半导体",
    "芯片": "半导体",
    "集成电路": "半导体",
    "国产替代": "半导体",
    "机器人": "机器人",
    "人形机器人": "机器人",
    "减速器": "机器人",
    "光伏": "光伏",
    "储能": "储能",
    "海上风电": "海风",
    "海风": "海风",
    "创新药": "创新药",
    "CXO": "创新药",
    "军工": "国防",
    "国防": "国防",
    "信创": "信创",
    "数据要素": "数据要素",
    "消费电子": "消费电子",
    "汽车": "新能源汽车",
    "新能源": "新能源汽车",
    "以旧换新": "以旧换新",
}


class MarketHeatScanner:
    """Detect hot concepts from market momentum data."""

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        data_collector: Optional[DataCollector] = None,
    ):
        self.settings = settings
        self.cache = cache
        self.collector = data_collector or DataCollector(settings, cache)

    async def scan(self, trade_date: str = "") -> list[HotSignal]:
        """Fetch hot stocks and fund flows, extract hot concepts.

        If the primary trade_date yields no data (common on non-trading days
        or when data sources don't serve historical data), automatically
        retries with recent trading days.

        Each date attempt is individually timed out to avoid a single slow
        API call consuming the entire scout time budget.
        """
        if not trade_date:
            from datetime import date
            trade_date = date.today().strftime("%Y-%m-%d")

        # Try primary date first, then fallback to recent trading days
        dates_to_try = get_recent_trade_dates(trade_date, count=5)
        for attempt_date in dates_to_try:
            try:
                results = await asyncio.wait_for(
                    self._scan_for_date(attempt_date),
                    timeout=15,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "MarketHeatScanner: _scan_for_date(%s) timed out after 15s, trying next date",
                    attempt_date,
                )
                continue
            except Exception as exc:
                logger.warning(
                    "MarketHeatScanner: _scan_for_date(%s) failed: %s, trying next date",
                    attempt_date,
                    exc,
                )
                continue
            if results:
                if attempt_date != trade_date:
                    logger.info(
                        "MarketHeatScanner: primary date %s had no data, "
                        "using data from %s instead (%d hot concepts)",
                        trade_date, attempt_date, len(results),
                    )
                return results

        logger.warning(
            "MarketHeatScanner: no hot concept data for %s or recent trading days",
            trade_date,
        )
        return []

    async def _scan_for_date(self, trade_date: str) -> list[HotSignal]:
        """Extract hot concepts for a single date. Returns empty list if no data."""
        concept_map: dict[str, dict] = {}

        # 1. Hot stocks (limit-up + reasons)
        try:
            market_heatmap = await self.collector.fetch_market_heatmap(date=trade_date)
            if market_heatmap:
                for item in market_heatmap[:50]:
                    code = item.get("code", "")
                    name = item.get("name", "")
                    reason = item.get("reason", "")
                    concept = self._extract_concept(reason, name)

                    if concept not in concept_map:
                        concept_map[concept] = {
                            "stocks": [],
                            "reasons": [],
                            "total_order_flow_profile": 0.0,
                        }
                    concept_map[concept]["stocks"].append(code)
                    if reason:
                        concept_map[concept]["reasons"].append(reason)
        except Exception as e:
            logger.warning("MarketHeatScanner: market_heatmap failed: %s", e)

        # 2. Fund flow per concept (try top concepts only)
        for concept in list(concept_map.keys())[:10]:
            try:
                # Approximate: use first stock as proxy for concept fund flow
                stocks = concept_map[concept]["stocks"]
                if stocks:
                    ff = await self.collector.fetch_order_flow_profile(stocks[0])
                    if ff and ff.get("net_inflow"):
                        concept_map[concept]["total_order_flow_profile"] += float(
                            ff.get("net_inflow", 0)
                        )
            except Exception as e:
                logger.debug("MarketHeatScanner: order_flow_profile for %s failed: %s", concept, e)

        # 3. Build HotSignal list
        results: list[HotSignal] = []
        for concept, data in concept_map.items():
            stock_count = len(data["stocks"])
            order_flow_profile = data["total_order_flow_profile"]

            # Heat level: stock count (0-6) + fund flow (0-4)
            stock_score = min(stock_count * 1.2, 6.0)
            fund_score = min(order_flow_profile / 1e8, 4.0) if order_flow_profile else 0.0
            heat_level = round(min(stock_score + fund_score, 10.0), 1)

            evidence_parts = [f"{stock_count}股涨停"]
            if order_flow_profile > 0:
                evidence_parts.append(f"资金净流入{order_flow_profile/1e8:.1f}亿")
            unique_reasons = list(set(data["reasons"]))[:3]
            if unique_reasons:
                evidence_parts.append(f"原因: {'; '.join(unique_reasons)}")

            results.append(
                HotSignal(
                    concept=concept,
                    heat_level=heat_level,
                    evidence="，".join(evidence_parts),
                    market_heatmap=data["stocks"],
                    order_flow_profile=order_flow_profile,
                )
            )

        # Sort by heat_level desc
        results.sort(key=lambda h: h.heat_level, reverse=True)
        logger.info(
            "MarketHeatScanner: detected %d hot concepts for %s",
            len(results),
            trade_date,
        )
        return results[:10]  # Top 10 concepts

    def _extract_concept(self, reason: str, stock_name: str) -> str:
        """Extract canonical concept from limit-up reason text."""
        text = f"{reason}{stock_name}"

        # Direct mapping
        for keyword, concept in _REASON_CONCEPT_MAP.items():
            if keyword in text:
                return concept

        # Regex fallback
        for pattern in _CONCEPT_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()

        return "其他"


