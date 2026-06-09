from fastapi.testclient import TestClient


def test_health_returns_version(client: TestClient) -> None:

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "version" in response.json()
    assert response.json()["workers"]["codex"]["available"] in {True, False}
    assert response.json()["workers"]["claude"]["available"] in {True, False}


def test_agent_card_is_public(client: TestClient) -> None:
    response = client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    assert response.json()["name"] == "PatchRelay"


def test_protected_paths_require_bearer_token(client: TestClient) -> None:
    response = client.get("/tasks")

    assert response.status_code == 401
