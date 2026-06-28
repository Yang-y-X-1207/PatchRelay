from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from patchrelay.config import RepoConfig, Settings, TestProfile as ConfigTestProfile
from helpers import init_git_repo


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    repo = init_git_repo(tmp_path / "repo")
    return Settings(
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        tests={"default": ConfigTestProfile(command=["python", "-c", "print('tests ok')"])},
    )


@pytest.fixture
def client(settings: Settings) -> Generator[TestClient, None, None]:
    from patchrelay.app import create_app

    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.server.token}"}
