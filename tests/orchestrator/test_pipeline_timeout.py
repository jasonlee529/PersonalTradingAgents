import asyncio
from types import SimpleNamespace

import pytest

from src.config import Settings
from src.orchestrator.pipeline import AnalysisPipeline
from src.orchestrator.state import AnalysisJob, JobStatus, StepStatus


class _MemoryJobStore:
    def __init__(self):
        self.saved = []

    async def save(self, job):
        self.saved.append(job.model_copy(deep=True))


class _Portfolio:
    async def get_holding(self, symbol):
        return SimpleNamespace(name=symbol)


class _TimedOutWrapper:
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
    pipeline.ta_wrapper = _TimedOutWrapper()

    job = AnalysisJob(id="timeout-1", symbol="600584")
    with pytest.raises(asyncio.TimeoutError):
        await pipeline.run_single("600584", job=job)

    assert job.status == JobStatus.ERROR
    assert job.error == "Analysis timed out after 0.01s"
    assert _step(job, "trader_plan").status == StepStatus.DONE
    assert _step(job, "risk_neutral").status == StepStatus.ERROR
    assert _step(job, "risk_neutral").detail == "Analysis timed out after 0.01s"
    assert _step(job, "final_decision").status == StepStatus.PENDING
    assert _step(job, "final_decision").detail == ""
    assert _step(job, "final_packaging").status == StepStatus.PENDING
    assert _step(job, "completed").status == StepStatus.PENDING
    assert all("Skipped: timed out" not in s.detail for s in job.steps)
