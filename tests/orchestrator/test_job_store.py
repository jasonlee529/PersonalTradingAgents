import pytest


@pytest.mark.asyncio
async def test_claim_next_pending_marks_one_job_running(test_settings):
    from src.orchestrator.job_store import JobStore
    from src.orchestrator.state import AnalysisJob

    store = JobStore(test_settings.analysis_db_path)
    await store.init_db()
    first = AnalysisJob(id="job1", symbol="AAA")
    second = AnalysisJob(id="job2", symbol="BBB")
    await store.save(first)
    await store.save(second)

    claimed = await store.claim_next_pending()

    assert claimed is not None
    assert claimed.id == "job1"
    assert claimed.status.value == "running"

    stored_first = await store.get("job1")
    stored_second = await store.get("job2")
    assert stored_first.status.value == "running"
    assert stored_second.status.value == "pending"
