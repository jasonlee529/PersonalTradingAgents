import pytest
from fastapi.testclient import TestClient
from src.api.main import create_app


@pytest.fixture
def api_client(test_settings):
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client


class TestAnalysisEndpoints:
    """End-to-end tests for analysis job lifecycle, status with steps, and feedback."""

    def test_create_analysis_job(self, api_client):
        resp = api_client.post("/api/analysis/", json={"symbol": "600519"})
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["symbol"] == "600519"
        assert data["status"] == "pending"
        assert data["steps"] == []

    def test_analysis_status_with_steps(self, api_client):
        # Create a job
        resp = api_client.post("/api/analysis/", json={
            "symbol": "000001",
            "analysts": ["market", "news"],
        })
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        # Fetch status — should include empty steps list for pending job
        resp = api_client.get(f"/api/analysis/{job_id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["symbol"] == "000001"
        assert "steps" in data
        assert isinstance(data["steps"], list)
        assert data["status"] == "pending"

    def test_list_analysis_jobs(self, api_client):
        # Create a job first
        api_client.post("/api/analysis/", json={"symbol": "TEST002"})

        resp = api_client.get("/api/analysis/jobs?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_analysis_jobs_includes_stock_name(self, api_client):
        api_client.post("/api/portfolio/holdings", json={
            "symbol": "TEST003",
            "name": "Test Stock",
            "market": "CN",
        })
        api_client.post("/api/analysis/", json={"symbol": "TEST003"})

        resp = api_client.get("/api/analysis/jobs?limit=10")
        assert resp.status_code == 200
        jobs = resp.json()
        job = next(item for item in jobs if item["symbol"] == "TEST003")
        assert job["stock_name"] == "Test Stock"

    def test_feedback_submit_and_retrieve(self, api_client):
        # Create a job
        resp = api_client.post("/api/analysis/", json={"symbol": "600519"})
        job_id = resp.json()["job_id"]

        # Submit upvote for a step
        resp = api_client.post(f"/api/analysis/{job_id}/feedback", json={
            "step_id": "analyst_market",
            "feedback_type": "upvote",
            "comment": "分析很到位",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Submit downvote for another step
        resp = api_client.post(f"/api/analysis/{job_id}/feedback", json={
            "step_id": "debate_bull",
            "feedback_type": "downvote",
        })
        assert resp.status_code == 200

        # Retrieve feedbacks
        resp = api_client.get(f"/api/analysis/{job_id}/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert len(data["feedbacks"]) == 2
        assert data["summary"]["upvotes"] == 1
        assert data["summary"]["downvotes"] == 1

        # Verify step-level details
        fb = data["feedbacks"]
        assert fb[0]["step_id"] == "analyst_market"
        assert fb[0]["feedback_type"] == "upvote"
        assert fb[0]["comment"] == "分析很到位"
        assert fb[1]["step_id"] == "debate_bull"
        assert fb[1]["feedback_type"] == "downvote"

    def test_feedback_for_nonexistent_job(self, api_client):
        resp = api_client.post("/api/analysis/nonexistent/feedback", json={
            "step_id": "analyst_market",
            "feedback_type": "upvote",
        })
        # Should still return 200 with error in body (current API behavior)
        assert resp.status_code == 200
        assert "error" in resp.json()

    def test_job_output_files_endpoint(self, api_client):
        resp = api_client.post("/api/analysis/", json={"symbol": "600519"})
        job_id = resp.json()["job_id"]

        resp = api_client.get(f"/api/analysis/{job_id}/files")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert "files" in data
