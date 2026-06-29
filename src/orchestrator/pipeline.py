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

_STEP_TO_RESUME_NODE = {
    "analyst_market": "Msg Clear Market",
    "analyst_sentiment": "Msg Clear Sentiment",
    "analyst_news": "Msg Clear News",
    "analyst_fundamentals": "Msg Clear Fundamentals",
    "analyst_catalyst": "Msg Clear Catalyst",
    "analyst_flow_risk": "Msg Clear Flow Risk",
    "debate_bull": "Bull Researcher",
    "debate_bear": "Bear Researcher",
    "debate_judge": "Research Manager",
    "trader_plan": "Trader",
    "risk_aggressive": "Aggressive Analyst",
    "risk_conservative": "Conservative Analyst",
    "risk_neutral": "Neutral Analyst",
    "final_decision": "Portfolio Manager",
}

_ANALYST_ARTIFACT_KEYS = {
    "analyst_market": "market_report",
    "analyst_sentiment": "sentiment_report",
    "analyst_news": "news_report",
    "analyst_fundamentals": "fundamentals_report",
    "analyst_catalyst": "catalyst_report",
    "analyst_flow_risk": "flow_risk_report",
}


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
        run_config = dict(config_overrides or {})
        stored_config = dict(job.config or {})
        trade_date = str(
            run_config.get("trade_date")
            or stored_config.get("trade_date")
            or datetime.now().strftime("%Y-%m-%d")
        )
        stored_config.setdefault("trade_date", trade_date)
        if "checkpoint_enabled" not in stored_config:
            stored_config["checkpoint_enabled"] = run_config.get("checkpoint_enabled", True)
        run_config.setdefault("trade_date", trade_date)
        run_config.setdefault("checkpoint_enabled", stored_config["checkpoint_enabled"])
        resume_seed = self._build_resume_seed(job)
        if run_config.get("checkpoint_enabled") and resume_seed:
            run_config.update(resume_seed)
        job.config = stored_config
        await self.job_store.save(job)

        try:
            job.update_progress("Running TradingAgents multi-agent analysis...")
            await self.job_store.save(job)

            holding = await self.portfolio.get_holding(symbol)
            company_name = holding.name if holding else None

            timeout_seconds = getattr(self.settings, "analysis_timeout_seconds", 3600) or 3600
            final_state, _ = await asyncio.wait_for(
                self.ta_wrapper.analyze(
                    symbol,
                    trade_date=trade_date,
                    selected_analysts=selected_analysts,
                    config_overrides=run_config,
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
            if job.config:
                job.config.pop("resume_failed_step", None)
            summary = decision[:200] if decision else "Analysis complete"
            job.complete(summary)
            await self.job_store.save(job)
            logger.info("Analysis complete for %s: %s", symbol, summary)

        except asyncio.TimeoutError:
            timeout_seconds = getattr(self.settings, "analysis_timeout_seconds", 3600) or 3600
            message = f"Analysis timed out after {timeout_seconds}s"
            logger.error("Analysis timed out for %s after %ss", symbol, timeout_seconds)
            await reporter.on_error(job.phase or "preparing", message)
            job.fail(message)
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

    def _build_resume_seed(self, job: AnalysisJob) -> dict:
        """Build a conservative checkpoint seed from persisted step artifacts.

        This is only a fallback for jobs created before checkpointing was on.
        If LangGraph already has a real checkpoint, the graph layer ignores
        this seed and resumes from the durable checkpoint instead.
        """
        if not job.steps:
            return {}

        failed_step_id = str((job.config or {}).get("resume_failed_step") or "")
        error_index = None
        for idx, step in enumerate(job.steps):
            if step.status == StepStatus.ERROR or (failed_step_id and step.step_id == failed_step_id):
                error_index = idx
                failed_step_id = step.step_id
                break
        if error_index is None:
            return {}

        resume_as_node = ""
        for step in reversed(job.steps[:error_index]):
            if step.status == StepStatus.DONE and step.step_id in _STEP_TO_RESUME_NODE:
                resume_as_node = _STEP_TO_RESUME_NODE[step.step_id]
                break
        if not resume_as_node:
            return {}

        resume_state: dict[str, object] = {}
        reports: dict[str, str] = {}
        detail_by_step = {
            step.step_id: step.detail
            for step in job.steps
            if step.status == StepStatus.DONE and step.detail
        }

        for step_id, key in _ANALYST_ARTIFACT_KEYS.items():
            value = detail_by_step.get(step_id, "")
            if value:
                resume_state[key] = value
                reports[key] = value
        if reports:
            resume_state["reports"] = reports

        bull_history = detail_by_step.get("debate_bull", "")
        bear_history = detail_by_step.get("debate_bear", "")
        debate_parts = [part for part in (bull_history, bear_history) if part]
        debate_count = len(debate_parts)
        if failed_step_id in {"debate_judge", "trader_plan", "risk_aggressive", "risk_conservative", "risk_neutral", "final_decision"}:
            debate_count = max(debate_count, 2 * self.settings.max_debate_rounds)
        resume_state["investment_debate_state"] = {
            "bull_history": bull_history,
            "bear_history": bear_history,
            "history": "\n".join(debate_parts),
            "current_response": bear_history or bull_history,
            "judge_decision": detail_by_step.get("debate_judge", ""),
            "count": debate_count,
        }

        if detail_by_step.get("debate_judge"):
            resume_state["investment_plan"] = detail_by_step["debate_judge"]
        if detail_by_step.get("trader_plan"):
            resume_state["trader_investment_plan"] = detail_by_step["trader_plan"]

        risk_order = [
            ("risk_aggressive", "aggressive_history", "Aggressive"),
            ("risk_conservative", "conservative_history", "Conservative"),
            ("risk_neutral", "neutral_history", "Neutral"),
        ]
        risk_parts: list[str] = []
        latest_speaker = ""
        risk_state: dict[str, object] = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
        }
        for step_id, key, speaker in risk_order:
            value = detail_by_step.get(step_id, "")
            risk_state[key] = value
            if value:
                risk_parts.append(value)
                latest_speaker = speaker
        risk_count = len(risk_parts)
        if failed_step_id == "final_decision":
            risk_count = max(risk_count, 3 * self.settings.max_risk_discuss_rounds)
        risk_state.update(
            {
                "history": "\n".join(risk_parts),
                "latest_speaker": latest_speaker,
                "current_aggressive_response": detail_by_step.get("risk_aggressive", ""),
                "current_conservative_response": detail_by_step.get("risk_conservative", ""),
                "current_neutral_response": detail_by_step.get("risk_neutral", ""),
                "judge_decision": detail_by_step.get("final_decision", ""),
                "count": risk_count,
            }
        )
        resume_state["risk_debate_state"] = risk_state

        if detail_by_step.get("final_decision"):
            resume_state["final_trade_decision"] = detail_by_step["final_decision"]

        return {
            "resume_as_node": resume_as_node,
            "resume_state": resume_state,
        }

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
