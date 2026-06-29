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


def test_worker_config_overrides_include_checkpoint_enabled():
    from src.orchestrator.job_worker import build_analysis_config_overrides

    overrides = build_analysis_config_overrides(
        {
            "output_language": "Chinese",
            "trade_date": "2026-06-16",
            "checkpoint_enabled": True,
            "analysts": ["market"],
            "unrelated": "ignored",
        }
    )

    assert overrides == {
        "output_language": "Chinese",
        "trade_date": "2026-06-16",
        "checkpoint_enabled": True,
    }
