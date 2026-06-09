from fastapi.testclient import TestClient

from patchrelay.app import create_app
from patchrelay.config import Settings


def test_health_returns_version() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "version" in response.json()


def test_agent_card_is_public() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    assert response.json()["name"] == "PatchRelay"


def test_protected_paths_require_bearer_token() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/tasks")

    assert response.status_code == 401
