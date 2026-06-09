import pytest
from fastapi.testclient import TestClient
from src.api.main import create_app


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
