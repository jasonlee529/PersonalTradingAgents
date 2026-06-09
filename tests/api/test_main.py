import pytest
from fastapi.testclient import TestClient
from src.api.main import create_app


@pytest.fixture
def client(test_settings):
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.headers["x-trace-id"]


def test_trace_id_header_is_respected(client):
    resp = client.get("/api/health", headers={"X-Trace-Id": "trace-test-1"})
    assert resp.status_code == 200
    assert resp.headers["x-trace-id"] == "trace-test-1"


def test_cors_headers(client):
    resp = client.options("/api/health", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    })
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers
