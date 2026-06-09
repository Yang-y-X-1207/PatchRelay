from fastapi.testclient import TestClient

from patchrelay.app import create_app


def test_health_returns_version() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "version" in response.json()
