from src.orchestrator.phase_reporter import PhaseReporter
from src.orchestrator.state import AnalysisJob, JobStatus, StepStatus


def _step(job: AnalysisJob, step_id: str):
    return next(s for s in job.steps if s.step_id == step_id)


async def test_analyst_step_does_not_complete_until_report_artifact_exists():
    job = AnalysisJob(id="phase-1", symbol="600519")
    reporter = PhaseReporter(job)

    await reporter.on_node_start("Market Analyst")
    await reporter.on_node_end("Market Analyst", {"messages": []})

    market = _step(job, "analyst_market")
    assert market.status == StepStatus.RUNNING
    assert not market.completed_at

    await reporter.on_node_start("tools_market")
    await reporter.on_node_end("tools_market", {"messages": []})

    market = _step(job, "analyst_market")
    prepare = _step(job, "prepare_data")
    assert market.status == StepStatus.RUNNING
    assert prepare.status == StepStatus.DONE

    await reporter.on_node_start("Market Analyst")
    await reporter.on_node_end("Market Analyst", {"market_report": "market ok"})

    market = _step(job, "analyst_market")
    assert market.status == StepStatus.DONE
    assert market.completed_at
    assert market.detail == "market ok"


async def test_starting_next_step_does_not_force_running_step_done():
    job = AnalysisJob(id="phase-2", symbol="600519")
    reporter = PhaseReporter(job)

    await reporter.on_node_start("data_start")
    await reporter.on_node_start("Market Analyst")

    prepare = _step(job, "prepare_data")
    market = _step(job, "analyst_market")
    assert prepare.status == StepStatus.DONE
    assert market.status == StepStatus.RUNNING


async def test_current_phase_moves_to_sentiment_even_if_market_waits_for_artifact():
    job = AnalysisJob(id="phase-3", symbol="600519")
    reporter = PhaseReporter(job)

    await reporter.on_node_start("Market Analyst")
    await reporter.on_node_end("Market Analyst", {"messages": []})
    await reporter.on_node_start("Sentiment Analyst")

    market = _step(job, "analyst_market")
    sentiment = _step(job, "analyst_sentiment")
    assert market.status == StepStatus.RUNNING
    assert sentiment.status == StepStatus.RUNNING
    assert job.phase == "analyst_sentiment"


async def test_on_error_marks_job_error_status():
    job = AnalysisJob(id="phase-4", symbol="600519")
    reporter = PhaseReporter(job)

    await reporter.on_node_start("Market Analyst")
    await reporter.on_error("Market Analyst", "boom")

    market = _step(job, "analyst_market")
    assert market.status == StepStatus.ERROR
    assert market.detail == "boom"
    assert job.status == JobStatus.ERROR
