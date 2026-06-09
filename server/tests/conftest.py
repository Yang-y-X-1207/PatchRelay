from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from patchrelay.app import create_app
from patchrelay.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def client(settings: Settings) -> Generator[TestClient, None, None]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.server.token}"}
