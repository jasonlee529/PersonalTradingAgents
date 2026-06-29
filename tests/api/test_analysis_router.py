import pytest
import asyncio
from fastapi.testclient import TestClient
from src.api.main import create_app
from src.orchestrator.state import AnalysisJob, JobStatus


@pytest.fixture
def client(test_settings):
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client


def test_start_analysis_mocked(client):
    resp = client.post("/api/analysis/", json={"symbol": "TEST"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "TEST"
    assert data["status"] == "pending"


def test_start_analysis_enables_checkpoint_by_default(client):
    resp = client.post("/api/analysis/", json={"symbol": "TEST"})
    assert resp.status_code == 200

    services = client.app.state.services
    job = asyncio.run(services.job_store.get(resp.json()["job_id"]))

    assert job.config["checkpoint_enabled"] is True
    assert job.config["trade_date"]


def test_retry_backfills_resume_config(client):
    services = client.app.state.services
    job = AnalysisJob(id="retry-1", symbol="600519")
    job.status = JobStatus.ERROR
    job.phase = "debate_judge"
    asyncio.run(services.job_store.save(job))

    resp = client.post("/api/analysis/retry-1/retry")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    stored = asyncio.run(services.job_store.get("retry-1"))
    assert stored.config["checkpoint_enabled"] is True
    assert stored.config["trade_date"]
    assert stored.config["resume_failed_step"] == "debate_judge"
