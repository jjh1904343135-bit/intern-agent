from fastapi.testclient import TestClient

from app.core.providers.factory import get_provider
from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["provider"] == get_provider().name
