"""SectorDiscoveryPipeline — orchestrates the discovery workflow.

Phase 0: PolicyMiner — extract policy signals from news/announcements
Phase 1a: MarketHeatScanner — detect hot concepts (signal source only)
Phase 1b: ChainMapper — LLM-driven upstream reasoning (needs HotSignal + PolicySignal)
Phase 1c: FundAnalyst — institutional mismatch screening
Phase 1d: ValueDigger — fundamental value screening
Phase 2: PolicyScout — cross-match policy + chain signals to pick stocks
Phase 3: SectorAggregator — merge + cross-validate + classify
Phase 4: SectorRanker — 7-dimension independent scoring
Phase 5: StockScreener — category-specific filtering
Phase 6: DirectionReportBuilder — data-driven markdown output
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from src.agents.sector_discovery.aggregator import SectorAggregator
from src.agents.sector_discovery.models import DirectionReport
from src.agents.sector_discovery.policy_miner import PolicyMiner
from src.agents.sector_discovery.ranker import SectorRanker
from src.agents.sector_discovery.report_builder import DirectionReportBuilder
from src.agents.sector_discovery.screener import StockScreener
from src.agents.sector_discovery.scanners.chain_mapper import ChainMapper
from src.agents.sector_discovery.scanners.correction_scanner import CorrectionScanner
from src.agents.sector_discovery.scanners.fund_analyst import FundAnalyst
from src.agents.sector_discovery.scanners.market_heat import MarketHeatScanner
from src.agents.sector_discovery.scanners.market_breadth_scanner import MarketBreadthScanner
from src.agents.sector_discovery.scanners.news_analyst import NewsAnalyst
from src.agents.sector_discovery.scanners.policy_scout import PolicyScout
from src.agents.sector_discovery.scanners.sector_ranking_scanner import SectorRankingScanner
from src.agents.sector_discovery.scanners.value_digger import ValueDigger
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector
from src.utils.trading_dates import normalize_trade_date

logger = logging.getLogger(__name__)


class SectorDiscoveryPipeline:
    """Run sector discovery scans and produce direction recommendations."""

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        data_collector: Optional[DataCollector] = None,
    ):
        self.settings = settings
        self.cache = cache
        self.collector = data_collector or DataCollector(settings, cache)

    async def run(
        self,
        board_code: Optional[str] = None,
        timeout_per_scanner: float = 30.0,
    ) -> DirectionReport:
        """Run the full discovery pipeline and produce a DirectionReport.

        Args:
            board_code: If given, narrow scan to a specific board.
            timeout_per_scanner: Max seconds per scanner before giving up.

        Returns:
            DirectionReport with aggregated sector snapshots.
        """
        date_str = normalize_trade_date(datetime.now().strftime("%Y-%m-%d"))

        # ── Phase 0: PolicyMiner + NewsAnalyst (parallel) ────────────────
        policy_signals, news_signals = await self._run_phase0_parallel()

        # ── Phase 1a: MarketHeatScanner ─────────────────────────────────────
        hot_signals = await self._run_phase1a_market_heat(date_str)

        # ── Phase 1b: ChainMapper ─────────────────────────────────────────
        chain_signals = await self._run_phase1b_chain_mapper(hot_signals, policy_signals)

        # ── Phase 1c & 1d: FundAnalyst + ValueDigger (parallel) ───────────
        fund_signals, value_signals = await self._run_phase1cd_fund_value(
            board_code, timeout_per_scanner
        )

        # ── Phase 1e & 1f: CorrectionScanner + SectorRankingScanner ───────
        correction_signals, momentum_signals = await self._run_phase1ef_correction_ranking(
            timeout_per_scanner
        )

        # ── Phase 2: PolicyScout ──────────────────────────────────────────
        policy_stock_signals = await self._run_phase2_policy_scout(
            policy_signals, chain_signals
        )

        # ── Phase 2b: MarketBreadthScanner ────────────────────────────────
        market_breadth = await self._run_phase2b_market_breadth()

        # ── Phase 3: Aggregate all stock signals ──────────────────────────
        all_stock_signals = (
            fund_signals + value_signals + policy_stock_signals +
            correction_signals + self._news_signals_to_stock_signals(news_signals)
        )
        aggregated = SectorAggregator().aggregate(all_stock_signals)
        logger.info("Phase 3 Aggregator: %d sectors from %d signals", len(aggregated), len(all_stock_signals))

        # ── Phase 4: Rank ─────────────────────────────────────────────────
        ranked = SectorRanker().rank(aggregated)
        logger.info("Phase 4 Ranker: ranked %d sectors", len(ranked))

        # ── Phase 5: Screen ───────────────────────────────────────────────
        screened = StockScreener().screen(ranked)
        logger.info("Phase 5 Screener: %d sectors after screening", len(screened))

        # ── Phase 5.5: Fetch market overview for context ──────────────────
        market_overview = await self._fetch_market_overview()
        news_context = await self._fetch_news_context()

        # ── Phase 6: Build report ─────────────────────────────────────────
        report = await DirectionReportBuilder().build(
            screened,
            date=date_str,
            market_overview=market_overview,
            news_context=news_context,
            policy_signals=policy_signals,
            chain_signals=chain_signals,
            settings=self.settings,
        )
        logger.info("Phase 6 ReportBuilder: built report with %d sectors for %s", len(report.sectors), date_str)

        logger.info("Sector discovery report generated (not persisted to legacy store)")
        return report

    async def _run_phase0_policy_miner(self) -> list:
        """Phase 0: Extract policy signals from news and announcements."""
        try:
            # Fetch news from multiple sources
            news_items: list[dict] = []
            try:
                global_news = await self.collector.get_global_news(look_back_days=3, limit=50)
                if global_news:
                    news_items.extend(global_news)
            except Exception as e:
                logger.warning("PolicyMiner: global news failed: %s", e)

            # Fetch announcements
            announcements: list[dict] = []
            try:
                from src.data.sources.cninfo_source import CninfoSource
                cninfo = CninfoSource(self.settings)
                announcements = await cninfo.get_announcements(limit=30)
            except Exception as e:
                logger.debug("PolicyMiner: announcements failed: %s", e)

            miner = PolicyMiner()
            signals = miner.mine(news_items, announcements)
            logger.info("PolicyMiner: extracted %d policy signals", len(signals))
            return signals
        except Exception as e:
            logger.warning("Phase 0 PolicyMiner failed: %s", e)
            return []

    async def _run_phase1a_market_heat(self, trade_date: str = "") -> list:
        """Phase 1a: Detect hot concepts from market momentum."""
        try:
            scanner = MarketHeatScanner(self.settings, self.cache, self.collector)
            hot_signals = await scanner.scan(trade_date=trade_date)
            logger.info("MarketHeatScanner: detected %d hot concepts", len(hot_signals))
            return hot_signals
        except Exception as e:
            logger.warning("Phase 1a MarketHeatScanner failed: %s", e)
            return []

    async def _run_phase1b_chain_mapper(self, hot_signals, policy_signals) -> list:
        """Phase 1b: LLM-driven supply chain reasoning."""
        try:
            mapper = ChainMapper(self.settings, self.cache, self.collector)
            chain_signals = await mapper.analyze(hot_signals, policy_signals)
            logger.info("ChainMapper: returned %d chain signals", len(chain_signals))
            return chain_signals
        except Exception as e:
            logger.warning("Phase 1b ChainMapper failed: %s", e)
            return []

    async def _run_phase1cd_fund_value(
        self, board_code: Optional[str], timeout: float
    ) -> tuple[list, list]:
        """Phase 1c & 1d: FundAnalyst + ValueDigger in parallel."""
        fund_scanner = FundAnalyst(self.settings, self.cache, self.collector)
        value_scanner = ValueDigger(self.settings, self.cache, self.collector)

        tasks = [
            asyncio.wait_for(fund_scanner.scan(board_code), timeout=timeout),
            asyncio.wait_for(value_scanner.scan(board_code), timeout=timeout),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        fund_result = results[0] if not isinstance(results[0], Exception) else []
        value_result = results[1] if not isinstance(results[1], Exception) else []

        if isinstance(fund_result, Exception):
            logger.warning("FundAnalyst failed: %s", fund_result)
            fund_signals = []
        else:
            fund_signals = fund_result.stocks if hasattr(fund_result, "stocks") else fund_result
            logger.info("FundAnalyst: returned %d signals", len(fund_signals))

        if isinstance(value_result, Exception):
            logger.warning("ValueDigger failed: %s", value_result)
            value_signals = []
        else:
            value_signals = value_result.stocks if hasattr(value_result, "stocks") else value_result
            logger.info("ValueDigger: returned %d signals", len(value_signals))

        return fund_signals, value_signals

    async def _run_phase2_policy_scout(self, policy_signals, chain_signals) -> list:
        """Phase 2: Cross-match policy + chain signals to pick stocks."""
        try:
            scout = PolicyScout(self.settings, self.cache, self.collector)
            policy_stock_signals = await scout.scan(policy_signals, chain_signals)
            logger.info("PolicyScout: returned %d signals", len(policy_stock_signals))
            return policy_stock_signals
        except Exception as e:
            logger.warning("Phase 2 PolicyScout failed: %s", e)
            return []

    async def _fetch_market_overview(self) -> dict | None:
        """Fetch indices, market stats, and sector rankings for report context."""
        try:
            indices, stats, rankings, northbound = await asyncio.gather(
                self.collector.get_market_indices(),
                self.collector.get_market_statistics(),
                self.collector.get_sector_rankings(n=5),
                self.collector.fetch_cross_border_flow(include_history=False),
                return_exceptions=True,
            )
            result: dict = {}
            if indices and not isinstance(indices, Exception):
                result["indices"] = indices
            if stats and not isinstance(stats, Exception):
                result["statistics"] = stats
            if rankings and not isinstance(rankings, Exception):
                result["sector_rankings"] = {"top": rankings[0], "bottom": rankings[1]}
            if northbound and not isinstance(northbound, Exception):
                result["northbound_flow"] = northbound
            return result if result else None
        except Exception as e:
            logger.warning("Market overview fetch failed: %s", e)
            return None

    async def _fetch_news_context(self) -> str:
        """Aggregate news from multiple sources for LLM context."""
        parts: list[str] = []
        try:
            global_news = await self.collector.get_global_news(look_back_days=3, limit=30)
            if global_news:
                parts.append("## 财经快讯")
                for item in global_news[:15]:
                    title = item.get("title", "")
                    content = item.get("content", "")
                    source = item.get("source", "")
                    time_str = item.get("time", "")
                    parts.append(f"- [{source}] {title} ({time_str})")
                    if content:
                        parts.append(f"  {content[:100]}")
        except Exception as e:
            logger.debug("News context global news failed: %s", e)

        try:
            from src.data.sources.cninfo_source import CninfoSource
            cninfo = CninfoSource(self.settings)
            announcements = await cninfo.get_announcements(limit=20)
            if announcements:
                parts.append("\n## 重要公告")
                for item in announcements[:10]:
                    title = item.get("title", "")
                    stock = item.get("stock_name", "")
                    parts.append(f"- [{stock}] {title}")
        except Exception as e:
            logger.debug("News context announcements failed: %s", e)

        return "\n".join(parts)

    async def _run_phase0_parallel(self) -> tuple[list, list]:
        """Phase 0: PolicyMiner + NewsAnalyst in parallel."""
        tasks = [
            self._run_phase0_policy_miner(),
            self._run_phase0_news_analyst(),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        policy_result = results[0] if not isinstance(results[0], Exception) else []
        news_result = results[1] if not isinstance(results[1], Exception) else []
        if isinstance(policy_result, Exception):
            logger.warning("PolicyMiner failed: %s", policy_result)
            policy_result = []
        if isinstance(news_result, Exception):
            logger.warning("NewsAnalyst failed: %s", news_result)
            news_result = []
        return policy_result, news_result

    async def _run_phase0_news_analyst(self) -> list:
        """Phase 0b: Extract investment signals from news."""
        try:
            analyst = NewsAnalyst(self.settings, self.cache, self.collector)
            signals = await analyst.scan()
            logger.info("NewsAnalyst: extracted %d news signals", len(signals))
            return signals
        except Exception as e:
            logger.warning("Phase 0b NewsAnalyst failed: %s", e)
            return []

    async def _run_phase1ef_correction_ranking(
        self, timeout: float
    ) -> tuple[list, list]:
        """Phase 1e & 1f: CorrectionScanner + SectorRankingScanner in parallel."""
        correction_scanner = CorrectionScanner(self.settings, self.cache, self.collector)
        ranking_scanner = SectorRankingScanner(self.settings, self.cache, self.collector)

        tasks = [
            asyncio.wait_for(correction_scanner.scan(), timeout=timeout),
            asyncio.wait_for(ranking_scanner.scan(), timeout=timeout),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        correction_result = results[0] if not isinstance(results[0], Exception) else None
        ranking_result = results[1] if not isinstance(results[1], Exception) else []

        if isinstance(correction_result, Exception):
            logger.warning("CorrectionScanner failed: %s", correction_result)
            correction_signals = []
        else:
            correction_signals = correction_result.stocks if hasattr(correction_result, "stocks") else []
            logger.info("CorrectionScanner: returned %d signals", len(correction_signals))

        if isinstance(ranking_result, Exception):
            logger.warning("SectorRankingScanner failed: %s", ranking_result)
            momentum_signals = []
        else:
            momentum_signals = ranking_result
            logger.info("SectorRankingScanner: returned %d momentum signals", len(momentum_signals))

        return correction_signals, momentum_signals

    async def _run_phase2b_market_breadth(self):
        """Phase 2b: Compute market breadth context."""
        try:
            scanner = MarketBreadthScanner(self.settings, self.cache, self.collector)
            ctx = await scanner.scan()
            logger.info("MarketBreadthScanner: sentiment=%s score=%.1f", ctx.sentiment, ctx.score)
            return ctx
        except Exception as e:
            logger.warning("Phase 2b MarketBreadthScanner failed: %s", e)
            return None

    def _news_signals_to_stock_signals(self, news_signals: list) -> list:
        """Convert NewsSignals to StockSignals for aggregation.

        NewsSignals don't have specific stocks, so we skip direct aggregation.
        Instead, they feed into ReportBuilder as context.
        """
        return []


