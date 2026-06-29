import asyncio
from types import SimpleNamespace

import pytest

from src.config import Settings
from src.orchestrator.pipeline import AnalysisPipeline
from src.orchestrator.state import AnalysisJob, AnalysisStep, JobStatus, StepStatus


class _MemoryJobStore:
    def __init__(self):
        self.saved = []

    async def save(self, job):
        self.saved.append(job.model_copy(deep=True))


class _Portfolio:
    async def get_holding(self, symbol):
        return SimpleNamespace(name=symbol)


class _TimedOutWrapper:
    def __init__(self):
        self.calls = []

    async def analyze(
        self,
        symbol,
        *,
        trade_date,
        selected_analysts,
        config_overrides,
        company_name,
        phase_reporter,
    ):
        self.calls.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "selected_analysts": selected_analysts,
                "config_overrides": dict(config_overrides or {}),
                "company_name": company_name,
            }
        )
        await phase_reporter.on_node_start("Trader")
        await phase_reporter.on_node_end("Trader", {"trader_investment_plan": "plan done"})
        await phase_reporter.on_node_start("Neutral Analyst")
        await asyncio.sleep(1)
        return {}, None


def _step(job: AnalysisJob, step_id: str):
    return next(s for s in job.steps if s.step_id == step_id)


async def test_timeout_fails_current_node_without_completing_later_steps(tmp_path):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        analysis_timeout_seconds=1,
        raw_knowledge_db_path=tmp_path / "data" / "knowledge" / "raw" / "index.db",
    )
    settings.analysis_timeout_seconds = 0.01
    store = _MemoryJobStore()
    pipeline = AnalysisPipeline(
        settings=settings,
        cache=SimpleNamespace(),
        portfolio=_Portfolio(),
        job_store=store,
    )
    wrapper = _TimedOutWrapper()
    pipeline.ta_wrapper = wrapper

    job = AnalysisJob(id="timeout-1", symbol="600584")
    with pytest.raises(asyncio.TimeoutError):
        await pipeline.run_single(
            "600584",
            config_overrides={"trade_date": "2026-06-16"},
            job=job,
        )

    assert job.status == JobStatus.ERROR
    assert job.error == "Analysis timed out after 0.01s"
    assert job.config["trade_date"] == "2026-06-16"
    assert job.config["checkpoint_enabled"] is True
    assert wrapper.calls[0]["trade_date"] == "2026-06-16"
    assert wrapper.calls[0]["config_overrides"]["checkpoint_enabled"] is True
    assert _step(job, "trader_plan").status == StepStatus.DONE
    assert _step(job, "risk_neutral").status == StepStatus.ERROR
    assert _step(job, "risk_neutral").detail == "Analysis timed out after 0.01s"
    assert _step(job, "final_decision").status == StepStatus.PENDING
    assert _step(job, "final_decision").detail == ""
    assert _step(job, "final_packaging").status == StepStatus.PENDING
    assert _step(job, "completed").status == StepStatus.PENDING
    assert all("Skipped: timed out" not in s.detail for s in job.steps)


async def test_pipeline_builds_resume_seed_from_persisted_step_artifacts(tmp_path):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        raw_knowledge_db_path=tmp_path / "data" / "knowledge" / "raw" / "index.db",
        max_debate_rounds=2,
    )
    pipeline = AnalysisPipeline(
        settings=settings,
        cache=SimpleNamespace(),
        portfolio=_Portfolio(),
        job_store=_MemoryJobStore(),
    )
    job = AnalysisJob(
        id="resume-1",
        symbol="600584",
        config={"resume_failed_step": "debate_judge"},
        steps=[
            AnalysisStep(step_id="analyst_market", label="", role="", character="", status=StepStatus.DONE, detail="market"),
            AnalysisStep(step_id="analyst_sentiment", label="", role="", character="", status=StepStatus.DONE, detail="sentiment"),
            AnalysisStep(step_id="analyst_news", label="", role="", character="", status=StepStatus.DONE, detail="news"),
            AnalysisStep(step_id="analyst_fundamentals", label="", role="", character="", status=StepStatus.DONE, detail="fundamentals"),
            AnalysisStep(step_id="debate_bull", label="", role="", character="", status=StepStatus.DONE, detail="Bull Analyst: bull"),
            AnalysisStep(step_id="debate_bear", label="", role="", character="", status=StepStatus.DONE, detail="Bear Analyst: bear"),
            AnalysisStep(step_id="debate_judge", label="", role="", character="", status=StepStatus.PENDING),
        ],
    )

    seed = pipeline._build_resume_seed(job)

    assert seed["resume_as_node"] == "Bear Researcher"
    state = seed["resume_state"]
    assert state["market_report"] == "market"
    assert state["investment_debate_state"]["bull_history"] == "Bull Analyst: bull"
    assert state["investment_debate_state"]["bear_history"] == "Bear Analyst: bear"
    assert state["investment_debate_state"]["count"] == 4
