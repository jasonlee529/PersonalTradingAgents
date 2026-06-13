# src/orchestrator/pipeline.py
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from src.agents.analysis_memory import extract_rating, save_analysis_memory
from src.agents.trading_agents_wrapper import TradingAgentsWrapper
from src.config import Settings
from src.data.cache import DataCache
from src.knowledge.raw_store import RawStore
from src.orchestrator.job_store import JobStore
from src.orchestrator.phase_reporter import PhaseReporter
from src.orchestrator.state import AnalysisJob, StepStatus
from src.portfolio.manager import PortfolioManager

logger = logging.getLogger(__name__)


# Map final_state report keys to (analysis_node, label).
_REPORT_KIND_MAP = [
    ("market_report", "market_report", "Market Analysis"),
    ("sentiment_report", "sentiment_report", "Sentiment Analysis"),
    ("news_report", "news_report", "News Analysis"),
    ("fundamentals_report", "fundamentals_report", "Fundamentals Analysis"),
    ("catalyst_report", "catalyst_report", "Catalyst Analysis"),
    ("flow_risk_report", "flow_risk_report", "Flow Risk Analysis"),
    ("data_quality_summary", "data_quality_summary", "Data Quality Summary"),
    ("trader_investment_plan", "trader_investment_plan", "Trading Plan"),
    ("final_trade_decision", "final_trade_decision", "Final Decision"),
]


class AnalysisPipeline:
    """Coordinates the full analysis pipeline: portfolio -> data -> analysis -> raw."""

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        portfolio: PortfolioManager,
        job_store: JobStore,
        raw_store: Optional[RawStore] = None,
    ):
        self.settings = settings
        self.cache = cache
        self.portfolio = portfolio
        self.job_store = job_store
        self.raw_store = raw_store or RawStore(settings)
        self.ta_wrapper = TradingAgentsWrapper(
            settings=settings,
            cache=cache,
        )

    async def run_single(
        self,
        symbol: str,
        *,
        selected_analysts: list[str] | None = None,
        config_overrides: dict | None = None,
        job: AnalysisJob | None = None,
    ) -> AnalysisJob:
        """Run analysis for a single symbol using TradingAgents."""
        if job is None:
            job = AnalysisJob(id=str(uuid.uuid4())[:8], symbol=symbol)
        await self.job_store.save(job)
        job.start()
        await self.job_store.save(job)
        job.update_progress("Fetching historical context...")
        await self.job_store.save(job)

        reporter = PhaseReporter(job, self.job_store)

        try:
            job.update_progress("Running TradingAgents multi-agent analysis...")
            await self.job_store.save(job)

            trade_date = datetime.now().strftime("%Y-%m-%d")

            holding = await self.portfolio.get_holding(symbol)
            company_name = holding.name if holding else None

            timeout_seconds = getattr(self.settings, "analysis_timeout_seconds", 600) or 600
            final_state, _ = await asyncio.wait_for(
                self.ta_wrapper.analyze(
                    symbol,
                    trade_date=trade_date,
                    selected_analysts=selected_analysts,
                    config_overrides=config_overrides,
                    company_name=company_name,
                    phase_reporter=reporter,
                ),
                timeout=timeout_seconds,
            )

            decision = final_state.get("final_trade_decision", "")
            await reporter.on_finalizing("Saving raw analysis artifacts")
            job.update_progress("Saving to raw knowledge store...")
            await self.job_store.save(job)

            raw_sources = await self._save_reports_to_raw(symbol, trade_date, final_state)
            output_files = [
                str((self.settings.raw_knowledge_dir / src["content_path"]).resolve())
                for src in raw_sources
            ]

            ta_log = (
                self.settings.analysis_artifacts_dir
                / symbol
                / "TradingAgentsStrategy_logs"
                / f"full_states_log_{trade_date}.json"
            )
            if ta_log.exists():
                output_files.append(str(ta_log))

            job.output_files = output_files
            await reporter.on_finalized(
                "\n".join(["## Generated files"] + [f"- {path}" for path in output_files])
            )
            summary = decision[:200] if decision else "Analysis complete"
            job.complete(summary)
            await self.job_store.save(job)
            logger.info("Analysis complete for %s: %s", symbol, summary)

        except asyncio.TimeoutError:
            timeout_seconds = getattr(self.settings, "analysis_timeout_seconds", 600) or 600
            logger.error("Analysis timed out for %s after %ss", symbol, timeout_seconds)

            # Determine how much analysis actually completed.
            # Step IDs are ordered logically: prepare -> analysts -> debate ->
            # trader -> risk -> final_decision -> packaging.  Count how far we
            # got by finding the last step that has meaningful content.
            _STEP_PROGRESS = [
                "prepare_data",
                "analyst_market", "analyst_sentiment", "analyst_news",
                "analyst_fundamentals", "analyst_catalyst", "analyst_flow_risk",
                "debate_bull", "debate_bear", "debate_judge",
                "trader_plan",
                "risk_aggressive", "risk_conservative", "risk_neutral",
                "final_decision",
            ]
            _step_map = {s.step_id: s for s in job.steps}
            last_done_idx = -1
            for i, sid in enumerate(_STEP_PROGRESS):
                step = _step_map.get(sid)
                if step and (step.status == StepStatus.DONE or step.detail):
                    last_done_idx = i
                else:
                    break

            # Fix steps that have content but weren't marked DONE due to the
            # timeout race — update their status to reflect reality.
            for sid in _STEP_PROGRESS[: last_done_idx + 1]:
                step = _step_map.get(sid)
                if step and step.status == StepStatus.RUNNING and step.detail:
                    step.status = StepStatus.DONE
                    step.completed_at = step.completed_at or datetime.now()

            if last_done_idx >= _STEP_PROGRESS.index("trader_plan"):
                # At least all analysts + debate + trader plan completed.
                # This is genuinely useful analysis data even without the
                # final synthesis — mark the job as done, not failed.
                await reporter.on_complete()
                # Mark remaining steps that didn't run as skipped.
                _COMPLETION_STEP_IDS = [
                    sid for sid in _STEP_PROGRESS
                    if _STEP_PROGRESS.index(sid) > last_done_idx
                ] + ["final_packaging", "completed"]
                for sid in _COMPLETION_STEP_IDS:
                    step = _step_map.get(sid)
                    if step and step.status == StepStatus.PENDING:
                        step.status = StepStatus.DONE
                        step.detail = step.detail or "Skipped: timed out"
                        step.completed_at = step.completed_at or datetime.now()
                # If final_decision has content, include it in the summary.
                fd_step = _step_map.get("final_decision")
                if fd_step and fd_step.detail:
                    summary = fd_step.detail[:200]
                else:
                    last_step = _step_map.get(_STEP_PROGRESS[last_done_idx])
                    last_label = last_step.label if last_step else "analysis"
                    summary = f"Analysis timed out after {last_label} (partial — {last_done_idx + 1}/{len(_STEP_PROGRESS)} core steps done)"
                job.complete(summary)
                await self.job_store.save(job)
                logger.info(
                    "Recovering timed-out job %s: %d/%d core steps done, completing as partial",
                    symbol, last_done_idx + 1, len(_STEP_PROGRESS),
                )
                return job
            else:
                await reporter.on_error(
                    job.phase or "preparing",
                    f"Analysis timed out after {timeout_seconds}s (only {last_done_idx + 1} core steps completed)",
                )
                job.fail(
                    f"Analysis timed out after {timeout_seconds}s "
                    f"(only {last_done_idx + 1}/{len(_STEP_PROGRESS)} core steps completed)"
                )
                await self.job_store.save(job)
                raise
        except Exception as e:
            logger.error("Analysis failed for %s: %s", symbol, e)
            current_phase = job.phase or "preparing"
            await reporter.on_error(current_phase, str(e))
            if not job.error:
                job.fail(str(e))
            await self.job_store.save(job)
            raise

        return job

    async def run_all(self) -> list[AnalysisJob]:
        """Run analysis for all portfolio holdings."""
        symbols = await self.portfolio.list_symbols()
        if not symbols:
            logger.warning("No holdings to analyze")
            return []

        jobs = []
        for symbol in symbols:
            jobs.append(await self.run_single(symbol))
        return jobs

    def _format_full_report(self, result: dict) -> str:
        parts = []
        for key, label in [
            ("market_report", "Market Analysis"),
            ("sentiment_report", "Sentiment Analysis"),
            ("news_report", "News Analysis"),
            ("fundamentals_report", "Fundamentals Analysis"),
            ("catalyst_report", "Catalyst Analysis"),
            ("flow_risk_report", "Flow Risk Analysis"),
        ]:
            if result.get(key):
                parts.append(f"## {label}\n\n{result[key]}")

        debate = result.get("investment_debate_state", {})
        if debate.get("judge_decision"):
            parts.append(f"## Bull/Bear Debate\n\n**Decision:** {debate['judge_decision']}")

        if result.get("trader_investment_plan"):
            parts.append(f"## Trading Plan\n\n{result['trader_investment_plan']}")

        risk = result.get("risk_debate_state", {})
        if risk.get("judge_decision"):
            parts.append(f"## Risk Assessment\n\n**Decision:** {risk['judge_decision']}")

        if result.get("final_trade_decision"):
            parts.append(f"## Final Decision\n\n{result['final_trade_decision']}")

        return "\n\n".join(parts) if parts else "No analysis content."

    def _extract_rating(self, decision: str) -> str:
        return extract_rating(decision)

    async def _save_reports_to_raw(
        self, symbol: str, date_str: str, final_state: dict
    ) -> list[dict]:
        """Persist TradingAgents final_state nodes as immutable raw sources."""
        await self.raw_store.init_db()
        now = datetime.now().astimezone()
        run_time = now.strftime("%H%M%S")
        run_id = f"analysis:{symbol}:{date_str}:{run_time}"
        saved: list[dict] = []

        for key, analysis_node, label in _REPORT_KIND_MAP:
            content = final_state.get(key, "")
            if not content:
                continue
            saved.append(
                await self.raw_store.add_source(
                    source_kind="stock_analysis",
                    origin="agent",
                    title=f"{symbol} {date_str} {label}",
                    markdown=self._render_stock_analysis_markdown(
                        title=f"{symbol} {date_str} {label}",
                        symbol=symbol,
                        date_str=date_str,
                        analysis_node=analysis_node,
                        content=content,
                    ),
                    metadata={
                        "symbol": symbol,
                        "symbols": [symbol],
                        "trade_date": date_str,
                        "run_id": run_id,
                        "run_time": run_time,
                        "analysis_node": analysis_node,
                        "agent_flow": "trading_agents",
                        "tags": [f"stock/{symbol}", f"node/{analysis_node}"],
                    },
                )
            )

        for debate_key, analysis_node, label in [
            ("investment_debate_state", "bull_bear_debate", "Bull/Bear Debate"),
            ("risk_debate_state", "risk_debate", "Risk Assessment"),
        ]:
            content = self._format_debate_state(final_state.get(debate_key, {}))
            if not content:
                continue
            saved.append(
                await self.raw_store.add_source(
                    source_kind="stock_analysis",
                    origin="agent",
                    title=f"{symbol} {date_str} {label}",
                    markdown=self._render_stock_analysis_markdown(
                        title=f"{symbol} {date_str} {label}",
                        symbol=symbol,
                        date_str=date_str,
                        analysis_node=analysis_node,
                        content=content,
                    ),
                    metadata={
                        "symbol": symbol,
                        "symbols": [symbol],
                        "trade_date": date_str,
                        "run_id": run_id,
                        "run_time": run_time,
                        "analysis_node": analysis_node,
                        "agent_flow": "trading_agents",
                        "tags": [f"stock/{symbol}", f"node/{analysis_node}"],
                    },
                )
            )

        full_report = self._format_full_report(final_state)
        if full_report:
            saved.append(
                await self.raw_store.add_source(
                    source_kind="stock_analysis",
                    origin="agent",
                    title=f"{symbol} {date_str} Full Report",
                    markdown=self._render_stock_analysis_markdown(
                        title=f"{symbol} {date_str} Full Report",
                        symbol=symbol,
                        date_str=date_str,
                        analysis_node="full_report",
                        content=full_report,
                    ),
                    metadata={
                        "symbol": symbol,
                        "symbols": [symbol],
                        "trade_date": date_str,
                        "run_id": run_id,
                        "run_time": run_time,
                        "analysis_node": "full_report",
                        "agent_flow": "trading_agents",
                        "rating": self._extract_rating(
                            final_state.get("final_trade_decision", "")
                        ),
                        "tags": [f"stock/{symbol}", "node/full_report"],
                    },
                )
            )

        memory = await save_analysis_memory(
            self.raw_store,
            symbol=symbol,
            trade_date=date_str,
            run_id=run_id,
            run_time=run_time,
            final_trade_decision=final_state.get("final_trade_decision", ""),
            linked_full_report_source_id=self._find_source_id(
                saved,
                source_kind="stock_analysis",
                analysis_node="full_report",
            ),
        )
        if memory:
            saved.append(memory)
        return saved

    @staticmethod
    def _find_source_id(
        sources: list[dict],
        *,
        source_kind: str,
        analysis_node: str,
    ) -> str:
        for source in sources:
            if source.get("source_kind") != source_kind:
                continue
            metadata = source.get("metadata") or {}
            if metadata.get("analysis_node") == analysis_node:
                return source.get("source_id", "")
        return ""

    @staticmethod
    def _render_stock_analysis_markdown(
        *,
        title: str,
        symbol: str,
        date_str: str,
        analysis_node: str,
        content: str,
    ) -> str:
        return "\n".join(
            [
                f"# {title}",
                "",
                f"**Symbol:** {symbol}",
                f"**Trade date:** {date_str}",
                f"**Analysis node:** {analysis_node}",
                "",
                "---",
                "",
                content,
            ]
        )

    @staticmethod
    def _format_debate_state(state: dict) -> str:
        if not isinstance(state, dict) or not state.get("judge_decision"):
            return ""
        parts = [f"**Decision:** {state['judge_decision']}", ""]
        for key, label in [
            ("bull_history", "Bull Case"),
            ("bear_history", "Bear Case"),
            ("aggressive", "Aggressive View"),
            ("conservative", "Conservative View"),
            ("neutral", "Neutral View"),
            ("aggressive_history", "Aggressive View"),
            ("conservative_history", "Conservative View"),
            ("neutral_history", "Neutral View"),
        ]:
            if state.get(key):
                parts.extend([f"## {label}", "", str(state[key]), ""])
        return "\n".join(parts).strip()
