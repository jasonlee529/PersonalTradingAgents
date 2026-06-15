"""Coordinator — orchestrates the multi-agent direction analysis pipeline.

Pipeline:
  Phase 1: Scout      → discovers candidate directions
  Phase 2: Validator  → validates each candidate across 3 dimensions (parallel)
  Phase 3: Comparator → ranks and selects top 5 directions
  Phase 4: Deep Dive  → chain / catalyst / risk analysis per direction (parallel)
  Phase 5: Report     → build DirectionReport
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from src.agents.sector_discovery.comparator.comparator_agent import ComparatorAgent
from src.agents.sector_discovery.deep_dive.chain_analyst import ChainAnalyst
from src.agents.sector_discovery.deep_dive.catalyst_agent import CatalystAgent
from src.agents.sector_discovery.deep_dive.risk_agent import RiskAgent
from src.agents.sector_discovery.models import (
    AgentExecutionRecord,
    CandidateDirection,
    ChainAnalysisReport,
    CatalystTimeline,
    DeepAnalysis,
    DirectionContext,
    DirectionReport,
    RiskAssessment,
    SectorSnapshot,
    SelectedDirection,
    ValidationReport,
)
from src.agents.sector_discovery.report_builder import DirectionReportBuilder
from src.agents.sector_discovery.scout.scout_agent import ScoutAgent
from src.agents.sector_discovery.validator.validator_agent import ValidatorAgent
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector
from src.utils.trading_dates import normalize_trade_date

logger = logging.getLogger(__name__)

AGENT_TIMEOUTS = {
    "scout": 180,
    "validator": 30,
    "comparator": 20,
    "chain_analyst": 120,
    "catalyst": 90,
    "risk": 60,
}


class Coordinator:
    """Orchestrates all phases of the direction discovery pipeline."""

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        collector: DataCollector,
    ):
        self.settings = settings
        self.cache = cache
        self.collector = collector

        self.scout = ScoutAgent(settings, cache, collector)
        self.validator = ValidatorAgent(settings, cache, collector)
        self.comparator = ComparatorAgent()
        self.chain_analyst = ChainAnalyst(settings, cache, collector)
        self.catalyst_agent = CatalystAgent(settings, cache, collector)
        self.risk_agent = RiskAgent(settings, cache, collector)

    # ── Public API ────────────────────────────────────────────────────────

    async def run(
        self,
        context: DirectionContext,
        on_phase: Optional[callable] = None,
    ) -> DirectionReport:
        """Run the full pipeline and return a DirectionReport.

        Args:
            context: Shared state object with date, market_overview, etc.
            on_phase: Optional callback(phase, status, message, duration_ms) for progress reporting.

        Returns:
            DirectionReport with sector snapshots and summary.
        """
        requested_date = context.date
        context.date = normalize_trade_date(context.date)
        if requested_date != context.date:
            context.original_date = requested_date
            logger.info(
                "Coordinator: normalized requested date %s to trade date %s (non-trading day)",
                requested_date,
                context.date,
            )
        logger.info("Coordinator: starting pipeline for %s", context.date)

        def _notify(phase: str, status: str, message: str = "", duration_ms: int = 0):
            if on_phase:
                try:
                    on_phase(phase, status, message, duration_ms)
                except Exception:
                    pass

        # Phase 1: Scout
        _notify("scout", "running", "正在发现候选方向...")
        candidates = await self._phase1_scout(context)
        _notify("scout", "success" if candidates else "failure",
                f"发现 {len(candidates)} 个候选方向" if candidates else "未发现候选方向",
                sum(r.duration_ms for r in context.execution_log if r.phase == "scout"))
        if not candidates:
            return self._fallback_report(context, "Scout returned no candidate directions.")

        # Phase 2: Validator (parallel per candidate)
        _notify("validate", "running", "正在验证候选方向...")
        await self._phase2_validate(context, candidates)
        _notify("validate", "success",
                f"验证完成: {len(context.validation_results)} 份报告",
                sum(r.duration_ms for r in context.execution_log if r.phase == "validate"))

        # Phase 3: Comparator
        _notify("compare", "running", "正在排序筛选...")
        selected = await self._phase3_compare(context)
        _notify("compare", "success",
                f"选中 {len(selected)} 个方向" if selected else "暂无推荐方向",
                sum(r.duration_ms for r in context.execution_log if r.phase == "compare"))
        if not selected:
            return self._no_recommendation_report(context)

        # Phase 4: Deep Dive (parallel per direction)
        _notify("deep_dive", "running", "正在深度分析...")
        await self._phase4_deep_dive(context, selected)
        _notify("deep_dive", "success",
                f"深度分析完成: {len(selected)} 个方向",
                sum(r.duration_ms for r in context.execution_log if r.phase == "deep_dive"))

        # Phase 5: Build Report
        _notify("report", "running", "正在生成报告...")
        await self._ensure_report_context(context)
        report = await self._phase5_build_report(context, selected)
        _notify("report", "success",
                f"报告生成完成: {len(report.sectors)} 个方向",
                0)

        logger.info(
            "Coordinator: pipeline complete — %d sectors, %d log entries",
            len(report.sectors),
            len(context.execution_log),
        )

        return report

    # ── Pipeline Phases ───────────────────────────────────────────────────

    async def _phase1_scout(
        self,
        context: DirectionContext,
    ) -> list[CandidateDirection]:
        """Run scout.scan() with timeout."""
        start = time.monotonic()
        try:
            candidates = await asyncio.wait_for(
                self.scout.scan(context),
                timeout=AGENT_TIMEOUTS["scout"],
            )
            duration = int((time.monotonic() - start) * 1000)
            context.execution_log.append(
                AgentExecutionRecord(
                    agent_name="scout",
                    phase="scout",
                    status="success",
                    duration_ms=duration,
                    message=f"Discovered {len(candidates)} candidates",
                )
            )
            context.candidate_directions = candidates
            logger.info("Phase 1 Scout: %d candidates", len(candidates))
            return candidates
        except asyncio.TimeoutError:
            duration = int((time.monotonic() - start) * 1000)
            context.execution_log.append(
                AgentExecutionRecord(
                    agent_name="scout",
                    phase="scout",
                    status="timeout",
                    duration_ms=duration,
                    message="Scout timed out",
                )
            )
            logger.warning("Phase 1 Scout: timed out")
            return []
        except Exception as exc:
            duration = int((time.monotonic() - start) * 1000)
            context.execution_log.append(
                AgentExecutionRecord(
                    agent_name="scout",
                    phase="scout",
                    status="failure",
                    duration_ms=duration,
                    message=str(exc),
                )
            )
            logger.warning("Phase 1 Scout: failed — %s", exc)
            return []

    async def _phase2_validate(
        self,
        context: DirectionContext,
        candidates: list[CandidateDirection],
    ) -> None:
        """Run validator.validate() in parallel for each candidate."""
        loop = asyncio.get_event_loop()

        async def _validate_one(candidate: CandidateDirection) -> ValidationReport:
            start = time.monotonic()
            try:
                # ValidatorAgent.validate is sync — run in executor
                report = await asyncio.wait_for(
                    loop.run_in_executor(None, self.validator.validate, candidate, context),
                    timeout=AGENT_TIMEOUTS["validator"],
                )
                duration = int((time.monotonic() - start) * 1000)
                context.execution_log.append(
                    AgentExecutionRecord(
                        agent_name="validator",
                        phase="validate",
                        status="success",
                        duration_ms=duration,
                        message=f"{candidate.name}: {report.overall_status}",
                    )
                )
                return report
            except asyncio.TimeoutError:
                duration = int((time.monotonic() - start) * 1000)
                context.execution_log.append(
                    AgentExecutionRecord(
                        agent_name="validator",
                        phase="validate",
                        status="timeout",
                        duration_ms=duration,
                        message=f"{candidate.name}: timed out",
                    )
                )
                logger.warning("Validator: %s timed out", candidate.name)
                return self._flag_report(candidate)
            except Exception as exc:
                duration = int((time.monotonic() - start) * 1000)
                context.execution_log.append(
                    AgentExecutionRecord(
                        agent_name="validator",
                        phase="validate",
                        status="failure",
                        duration_ms=duration,
                        message=f"{candidate.name}: {exc}",
                    )
                )
                logger.warning("Validator: %s failed — %s", candidate.name, exc)
                return self._flag_report(candidate)

        tasks = [_validate_one(c) for c in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        reports: list[ValidationReport] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Validator task raised exception: %s", result)
                continue
            reports.append(result)

        context.validation_results = reports
        logger.info("Phase 2 Validator: %d reports from %d candidates", len(reports), len(candidates))

    def _flag_report(self, candidate: CandidateDirection) -> ValidationReport:
        """Create a FLAG report when validator fails for a candidate."""
        from src.agents.sector_discovery.models import DimensionValidation
        return ValidationReport(
            direction_name=candidate.name,
            overall_status="FLAG",
            fund_validation=DimensionValidation(dimension="fund", status="missing", score=candidate.confidence),
            policy_validation=DimensionValidation(dimension="policy", status="missing", score=candidate.confidence),
            sentiment_validation=DimensionValidation(dimension="sentiment", status="missing", score=candidate.confidence),
            score_after_validation=candidate.confidence,
            rejection_reason="",
            watch_points=["Validation failed — using candidate confidence as fallback score"],
        )

    async def _phase3_compare(self, context: DirectionContext) -> list[SelectedDirection]:
        """Run comparator.compare() with timeout and fallback."""
        start = time.monotonic()
        try:
            loop = asyncio.get_event_loop()
            selected = await asyncio.wait_for(
                loop.run_in_executor(None, self.comparator.compare, context),
                timeout=AGENT_TIMEOUTS["comparator"],
            )
            duration = int((time.monotonic() - start) * 1000)
            context.execution_log.append(
                AgentExecutionRecord(
                    agent_name="comparator",
                    phase="compare",
                    status="success",
                    duration_ms=duration,
                    message=f"Selected {len(selected)} directions",
                )
            )
            context.selected_directions = selected
            logger.info("Phase 3 Comparator: %d directions selected", len(selected))
            return selected
        except asyncio.TimeoutError:
            duration = int((time.monotonic() - start) * 1000)
            context.execution_log.append(
                AgentExecutionRecord(
                    agent_name="comparator",
                    phase="compare",
                    status="timeout",
                    duration_ms=duration,
                    message="Comparator timed out",
                )
            )
            logger.warning("Phase 3 Comparator: timed out — using fallback")
        except Exception as exc:
            duration = int((time.monotonic() - start) * 1000)
            context.execution_log.append(
                AgentExecutionRecord(
                    agent_name="comparator",
                    phase="compare",
                    status="failure",
                    duration_ms=duration,
                    message=str(exc),
                )
            )
            logger.warning("Phase 3 Comparator: failed — %s — using fallback", exc)

        # Fallback: sort valid reports by score_after_validation, take top 5
        valid_reports = [
            r for r in context.validation_results
            if r.overall_status in ("PASS", "FLAG")
        ]
        valid_reports.sort(key=lambda r: r.score_after_validation, reverse=True)

        selected: list[SelectedDirection] = []
        for rank, report in enumerate(valid_reports[:5], start=1):
            sel = SelectedDirection(
                name=report.direction_name,
                rank=rank,
                total_score=round(report.score_after_validation, 1),
                fund_score=round(report.fund_validation.score, 1),
                policy_score=round(report.policy_validation.score, 1),
                sentiment_score=round(report.sentiment_validation.score, 1),
                selection_reason="Fallback: sorted by validation score",
            )
            selected.append(sel)

        context.execution_log.append(
            AgentExecutionRecord(
                agent_name="comparator",
                phase="compare",
                status="fallback",
                duration_ms=0,
                message=f"Fallback selected {len(selected)} directions",
            )
        )
        context.selected_directions = selected
        logger.info("Phase 3 Comparator fallback: %d directions", len(selected))
        return selected

    async def _phase4_deep_dive(
        self,
        context: DirectionContext,
        selected: list[SelectedDirection],
    ) -> None:
        """Run chain_analyst, catalyst, risk in parallel per direction.

        Limit concurrency with a semaphore to avoid exhausting the thread-pool
        executor that LangChain's sync HTTP clients run in.
        """
        sem = asyncio.Semaphore(3)

        async def _analyze_direction(direction: SelectedDirection) -> None:
            start = time.monotonic()

            async def _chain() -> ChainAnalysisReport | None:
                try:
                    return await asyncio.wait_for(
                        self.chain_analyst.analyze(direction, context),
                        timeout=AGENT_TIMEOUTS["chain_analyst"],
                    )
                except Exception as exc:
                    logger.warning("ChainAnalyst: %s failed — %s", direction.name, exc)
                    return None

            async def _catalyst() -> CatalystTimeline | None:
                try:
                    return await asyncio.wait_for(
                        self.catalyst_agent.analyze(direction, context),
                        timeout=AGENT_TIMEOUTS["catalyst"],
                    )
                except Exception as exc:
                    logger.warning("CatalystAgent: %s failed — %s", direction.name, exc)
                    return None

            async def _risk() -> RiskAssessment | None:
                try:
                    return await asyncio.wait_for(
                        self.risk_agent.analyze(direction, context),
                        timeout=AGENT_TIMEOUTS["risk"],
                    )
                except Exception as exc:
                    logger.warning("RiskAgent: %s failed — %s", direction.name, exc)
                    return None

            async with sem:
                chain_result, catalyst_result, risk_result = await asyncio.gather(
                    _chain(), _catalyst(), _risk()
                )

            duration = int((time.monotonic() - start) * 1000)
            failed = sum(x is None for x in (chain_result, catalyst_result, risk_result))
            status: str = "success" if failed == 0 else "fallback" if failed < 3 else "failure"

            context.execution_log.append(
                AgentExecutionRecord(
                    agent_name="deep_dive",
                    phase="deep_dive",
                    status=status,  # type: ignore[arg-type]
                    duration_ms=duration,
                    message=f"{direction.name}: chain={chain_result is not None}, catalyst={catalyst_result is not None}, risk={risk_result is not None}",
                )
            )

            context.deep_analysis[direction.name] = DeepAnalysis(
                chain=chain_result,
                catalyst=catalyst_result,
                risk=risk_result,
            )

        await asyncio.gather(*[_analyze_direction(d) for d in selected])
        logger.info("Phase 4 Deep Dive: analyzed %d directions", len(selected))

    async def _ensure_report_context(self, context: DirectionContext) -> None:
        """Populate market/news context before asking the LLM to write a report."""
        if not context.market_overview:
            context.market_overview = await self._fetch_market_overview()
        if not context.news_context:
            context.news_context = await self._fetch_news_context()

    async def _fetch_market_overview(self) -> dict | None:
        """Fetch indices, market stats, and sector rankings for report context."""
        try:
            indices, stats, rankings = await asyncio.gather(
                self.collector.get_market_indices(),
                self.collector.get_market_statistics(),
                self.collector.get_sector_rankings(n=5),
                return_exceptions=True,
            )
            result: dict = {}
            if indices and not isinstance(indices, Exception):
                result["indices"] = indices
            if stats and not isinstance(stats, Exception):
                result["statistics"] = stats
            if rankings and not isinstance(rankings, Exception):
                result["sector_rankings"] = {"top": rankings[0], "bottom": rankings[1]}
            return result if result else None
        except Exception as e:
            logger.warning("Market overview fetch failed: %s", e)
            return None

    async def _fetch_news_context(self) -> str:
        """Aggregate recent market news and announcements for report context."""
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

    async def _phase5_build_report(
        self,
        context: DirectionContext,
        selected: list[SelectedDirection],
    ) -> DirectionReport:
        """Convert selected directions to SectorSnapshot list and build report."""
        snapshots = self._directions_to_snapshots(selected, context)

        builder = DirectionReportBuilder()
        report = await builder.build(
            snapshots=snapshots,
            date=context.date,
            market_overview=context.market_overview,
            news_context=context.news_context,
            settings=self.settings,
        )
        return report

    def _directions_to_snapshots(
        self,
        selected: list[SelectedDirection],
        context: DirectionContext,
    ) -> list[SectorSnapshot]:
        """Convert SelectedDirection objects to SectorSnapshot list."""
        snapshots: list[SectorSnapshot] = []
        for direction in selected:
            deep = context.deep_analysis.get(direction.name)
            tags = []
            candidate_metrics = {}
            # Find original candidate to get category
            for cand in context.candidate_directions:
                if cand.name == direction.name:
                    tags.append(cand.category)
                    candidate_metrics = dict(cand.raw_metrics or {})
                    break

            snapshot = SectorSnapshot(
                board_code="",
                name=direction.name,
                fund_score=direction.fund_score,
                policy_score=direction.policy_score,
                chain_score=getattr(deep.chain, "segments", []).__len__() * 1.5 if deep and deep.chain else 0.0,
                composite_score=direction.total_score,
                expectation_gap_score=direction.chain_depth_score,
                tags=tags,
                raw_metrics={
                    **candidate_metrics,
                    "selection_reason": direction.selection_reason,
                    "comparison_notes": direction.comparison_notes,
                    "eliminated_peers": direction.eliminated_peers,
                    "sentiment_score": direction.sentiment_score,
                },
            )
            snapshots.append(snapshot)
        return snapshots

    # ── Fallback & Persistence ────────────────────────────────────────────

    def _fallback_report(self, context: DirectionContext, reason: str) -> DirectionReport:
        """Return a fallback DirectionReport when pipeline fails early."""
        logger.warning("Coordinator fallback: %s", reason)
        date_info = context.date
        if context.is_non_trading_day:
            date_info = f"{context.date} (原始请求日期 {context.original_date} 为非交易日)"
        return DirectionReport(
            date=context.date,
            sectors=[],
            summary=(
                f"[Fallback] 方向分析未能完成。原因: {reason}\n\n"
                f"日期: {date_info}\n"
                "可能原因:\n"
                "• 非交易日运行，市场热度数据不可用\n"
                "• 数据源返回空数据或响应异常\n"
                "• 当日市场信号不足，未能通过筛选阈值\n\n"
                "建议: 在交易日运行，或检查数据源配置。"
            ),
        )

    def _no_recommendation_report(self, context: DirectionContext) -> DirectionReport:
        """Return a normal empty report when all candidates fail validation."""
        rejected = sum(1 for r in context.validation_results if r.overall_status == "REJECT")
        total = len(context.validation_results)
        logger.info(
            "Coordinator: no recommendation after validation, rejected=%d total=%d",
            rejected,
            total,
        )
        return DirectionReport(
            date=context.date,
            sectors=[],
            summary=(
                "\u4eca\u65e5\u6682\u65e0\u63a8\u8350\u65b9\u5411\u3002\n\n"
                "\u5019\u9009\u65b9\u5411\u5df2\u5b8c\u6210\u9a8c\u8bc1\uff0c\u4f46\u6ca1\u6709\u65b9\u5411\u8fbe\u5230\u63a8\u8350\u6807\u51c6\u3002"
                f"\u9a8c\u8bc1\u7ed3\u679c: {rejected}/{total} \u4e2a\u5019\u9009\u65b9\u5411\u88ab\u62d2\u7edd\u3002"
                "\u8fd9\u901a\u5e38\u4e0e\u5f53\u65e5\u8d44\u91d1\u3001\u70ed\u70b9\u3001\u65b0\u95fb\u6216\u677f\u5757\u6570\u636e\u4e0d\u8db3\u6709\u5173\u3002"
            ),
        )
