import pytest
from fastapi.testclient import TestClient
from src.api.main import create_app


@pytest.fixture
def api_client(test_settings):
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client
