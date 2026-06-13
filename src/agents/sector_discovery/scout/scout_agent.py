from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.agents.sector_discovery.models import (
    CandidateDirection,
    DirectionContext,
    SignalEvidence,
)
from src.agents.sector_discovery.llm_utils import SectorDiscoveryLLMError
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector
from src.utils.trading_dates import is_weekend

logger = logging.getLogger(__name__)

MIN_MARKET_HEAT = 4.0
MIN_MARKET_HEAT_LIMIT_UP = 3
MIN_MARKET_HEAT_ORDER_FLOW = 5e8
NOISY_MARKET_HEAT_CONCEPTS = {"其他", "未分类", ""}

# Relaxed thresholds for non-trading days or sparse data scenarios
MIN_MARKET_HEAT_RELAXED = 2.0
MIN_MARKET_HEAT_LIMIT_UP_RELAXED = 1
MIN_MARKET_HEAT_ORDER_FLOW_RELAXED = 1e8


class ScoutAgent:
    """Discovers candidate directions from market scanners."""

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        collector: DataCollector,
    ):
        self.settings = settings
        self.cache = cache
        self.collector = collector

    async def scan(self, context: DirectionContext) -> list[CandidateDirection]:
        """Run all scanners in parallel and produce candidate directions.

        On non-trading days or when market data is sparse, thresholds are
        automatically relaxed so that lower-confidence signals still pass
        through instead of producing an empty candidate list.
        """
        # Determine whether to use relaxed thresholds
        use_relaxed = context.is_non_trading_day or is_weekend(context.date)
        if use_relaxed:
            logger.info(
                "ScoutAgent: non-trading day detected (date=%s, original=%s), "
                "using relaxed thresholds",
                context.date, context.original_date or "N/A",
            )

        # Run all scanners concurrently
        results = await asyncio.gather(
            self._scan_market_heat(context.date),
            self._scan_policy(),
            self._scan_fund(),
            self._scan_value(),
            self._scan_news(),
            return_exceptions=True,
        )
        llm_errors = [result for result in results if isinstance(result, SectorDiscoveryLLMError)]
        if llm_errors:
            logger.warning(
                "ScoutAgent: %d LLM scanner(s) failed; continuing with non-LLM signals",
                len(llm_errors),
            )

        hot_signals = results[0] if not isinstance(results[0], Exception) else []
        policy_signals = results[1] if not isinstance(results[1], Exception) else []
        fund_signals = results[2] if not isinstance(results[2], Exception) else []
        value_signals = results[3] if not isinstance(results[3], Exception) else []
        news_signals = results[4] if not isinstance(results[4], Exception) else []

        logger.info(
            "ScoutAgent: scanner results — hot=%d policy=%d fund=%d value=%d news=%d",
            len(hot_signals), len(policy_signals),
            len(fund_signals), len(value_signals), len(news_signals),
        )

        # Convert scanner outputs to candidate directions
        candidates: list[CandidateDirection] = []
        candidates.extend(self._hot_signals_to_candidates(hot_signals, relaxed=use_relaxed))
        candidates.extend(self._policy_signals_to_candidates(policy_signals))
        candidates.extend(self._fund_signals_to_candidates(fund_signals))
        candidates.extend(self._value_signals_to_candidates(value_signals))
        candidates.extend(self._news_signals_to_candidates(news_signals))

        # If no candidates with strict/relaxed thresholds AND hot_signals had raw data,
        # try one more time with fully relaxed thresholds
        if not candidates and hot_signals:
            logger.info("ScoutAgent: retrying hot signals with fully relaxed thresholds")
            candidates.extend(self._hot_signals_to_candidates(hot_signals, relaxed=True))

        # Deduplicate by name
        seen: set[str] = set()
        deduped: list[CandidateDirection] = []
        for cand in candidates:
            if cand.name not in seen:
                seen.add(cand.name)
                deduped.append(cand)

        logger.info("ScoutAgent: discovered %d unique candidates", len(deduped))
        if not deduped and llm_errors:
            raise llm_errors[0]
        return deduped

    async def _scan_market_heat(self, trade_date: str = "") -> list:
        """Run MarketHeatScanner."""
        try:
            from src.agents.sector_discovery.scanners.market_heat import MarketHeatScanner
            scanner = MarketHeatScanner(self.settings, self.cache, self.collector)
            return await scanner.scan(trade_date=trade_date)
        except Exception as e:
            logger.warning("ScoutAgent: MarketHeatScanner failed: %s", e)
            return []

    async def _scan_policy(self) -> list:
        """Run PolicyMiner."""
        try:
            from src.agents.sector_discovery.policy_miner import PolicyMiner
            miner = PolicyMiner()
            news = await self.collector.get_global_news(look_back_days=3, limit=50)
            news = news if news else []
            return miner.mine(news, [])
        except Exception as e:
            logger.warning("ScoutAgent: PolicyMiner failed: %s", e)
            return []

    async def _scan_fund(self) -> list:
        """Run FundAnalyst."""
        try:
            from src.agents.sector_discovery.scanners.fund_analyst import FundAnalyst
            scanner = FundAnalyst(self.settings, self.cache, self.collector)
            result = await scanner.scan()
            return result.stocks if hasattr(result, "stocks") else result
        except Exception as e:
            logger.warning("ScoutAgent: FundAnalyst failed: %s", e)
            return []

    async def _scan_value(self) -> list:
        """Run ValueDigger."""
        try:
            from src.agents.sector_discovery.scanners.value_digger import ValueDigger
            scanner = ValueDigger(self.settings, self.cache, self.collector)
            result = await scanner.scan()
            return result.stocks if hasattr(result, "stocks") else result
        except Exception as e:
            logger.warning("ScoutAgent: ValueDigger failed: %s", e)
            return []

    async def _scan_news(self) -> list:
        """Run NewsAnalyst."""
        try:
            from src.agents.sector_discovery.scanners.news_analyst import NewsAnalyst
            scanner = NewsAnalyst(self.settings, self.cache, self.collector)
            return await scanner.scan()
        except SectorDiscoveryLLMError:
            raise
        except Exception as e:
            logger.warning("ScoutAgent: NewsAnalyst failed: %s", e)
            return []

    def _hot_signals_to_candidates(self, signals: list, *, relaxed: bool = False) -> list[CandidateDirection]:
        candidates = []
        for sig in signals:
            concept = getattr(sig, "concept", "")
            heat_level = float(getattr(sig, "heat_level", 0) or 0)
            order_flow_profile = float(getattr(sig, "order_flow_profile", 0) or 0)
            stock_count = len(getattr(sig, "market_heatmap", []))
            if not concept:
                continue
            if not self._is_actionable_hot_signal(concept, heat_level, stock_count, order_flow_profile, relaxed=relaxed):
                logger.info(
                    "ScoutAgent: skipped %s hot-money signal concept=%s heat=%.1f limit_up=%d order_flow_profile=%.0f",
                    "relaxed" if relaxed else "strict",
                    concept,
                    heat_level,
                    stock_count,
                    order_flow_profile,
                )
                continue
            evidence = SignalEvidence(
                source="market_heat",
                description=getattr(sig, "evidence", "热点概念"),
                strength=heat_level,
                data_snapshot={
                    "market_heatmap": getattr(sig, "market_heatmap", []),
                    "heat_level": heat_level,
                    "order_flow_profile": order_flow_profile,
                    "limit_up_count": stock_count,
                },
            )
            candidates.append(CandidateDirection(
                name=concept,
                category="热点追逐",
                confidence=min(heat_level, 10.0),
                evidence_signals=[evidence],
                raw_metrics={
                    "heat_level": heat_level,
                    "order_flow_profile": order_flow_profile,
                    "limit_up_count": stock_count,
                },
            ))
        return candidates

    def _is_actionable_hot_signal(
        self,
        concept: str,
        heat_level: float,
        limit_up_count: int,
        order_flow_profile: float,
        *,
        relaxed: bool = False,
    ) -> bool:
        """Keep only hot-money signals with enough breadth or fund confirmation.

        When *relaxed* is True (non-trading day or sparse data), use lower
        thresholds so weaker signals still pass through instead of being
        silently discarded.
        """
        if concept in NOISY_MARKET_HEAT_CONCEPTS:
            return False
        min_heat = MIN_MARKET_HEAT_RELAXED if relaxed else MIN_MARKET_HEAT
        min_limit_up = MIN_MARKET_HEAT_LIMIT_UP_RELAXED if relaxed else MIN_MARKET_HEAT_LIMIT_UP
        min_order_flow = MIN_MARKET_HEAT_ORDER_FLOW_RELAXED if relaxed else MIN_MARKET_HEAT_ORDER_FLOW
        if limit_up_count >= min_limit_up:
            return True
        if order_flow_profile >= min_order_flow:
            return True
        return heat_level >= min_heat

    def _policy_signals_to_candidates(self, signals: list) -> list[CandidateDirection]:
        candidates = []
        for sig in signals:
            keyword = getattr(sig, "keyword", "")
            if not keyword:
                continue
            industries = getattr(sig, "beneficiary_industries", [])
            name = f"{keyword}政策受益" if keyword else "政策受益"
            evidence = SignalEvidence(
                source="policy",
                description=f"{getattr(sig, 'level', '')}级政策",
                strength=7.0,
                data_snapshot={"industries": industries},
            )
            candidates.append(CandidateDirection(
                name=name,
                category="政策前瞻",
                confidence=7.0,
                evidence_signals=[evidence],
                raw_metrics={"policy_level": getattr(sig, "level", "")},
            ))
        return candidates

    def _fund_signals_to_candidates(self, signals: list) -> list[CandidateDirection]:
        candidates = []
        for sig in signals:
            name = getattr(sig, "name", "")
            if not name:
                continue
            evidence = SignalEvidence(
                source="fund",
                description="机构资金布局",
                strength=6.0,
            )
            candidates.append(CandidateDirection(
                name=name,
                category="机构错配",
                confidence=6.0,
                evidence_signals=[evidence],
            ))
        return candidates

    def _value_signals_to_candidates(self, signals: list) -> list[CandidateDirection]:
        candidates = []
        for sig in signals:
            name = getattr(sig, "name", "")
            if not name:
                continue
            evidence = SignalEvidence(
                source="value",
                description="价值低估信号",
                strength=6.0,
            )
            candidates.append(CandidateDirection(
                name=name,
                category="价值蓄势",
                confidence=6.0,
                evidence_signals=[evidence],
            ))
        return candidates

    def _news_signals_to_candidates(self, signals: list) -> list[CandidateDirection]:
        candidates = []
        for sig in signals:
            theme = getattr(sig, "theme", "")
            if not theme:
                continue
            evidence = SignalEvidence(
                source="news",
                description=getattr(sig, "reasoning", "")[:100],
                strength=getattr(sig, "catalyst_strength", 5.0),
            )
            candidates.append(CandidateDirection(
                name=theme,
                category="热点追逐",
                confidence=min(getattr(sig, "catalyst_strength", 5.0), 10.0),
                evidence_signals=[evidence],
            ))
        return candidates