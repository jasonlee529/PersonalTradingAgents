# tests/orchestrator/test_state.py
from src.orchestrator.state import AnalysisJob, JobStatus


def test_job_lifecycle():
    job = AnalysisJob(id="test-1", symbol="600519")
    assert job.status == JobStatus.PENDING

    job.start()
    assert job.status == JobStatus.RUNNING
    assert job.started_at is not None

    job.update_progress("Fetching data...")
    assert "Fetching" in job.progress

    job.complete("分析完成")
    assert job.status == JobStatus.DONE
    assert job.result_summary == "分析完成"


def test_job_failure():
    job = AnalysisJob(id="test-2", symbol="AAPL")
    job.start()
    job.fail("网络错误")
    assert job.status == JobStatus.ERROR
    assert "网络" in job.error
