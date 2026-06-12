from pathlib import Path

import pytest

from patchrelay.config import ServerConfig, Settings
from patchrelay.onboarding import (
    OnboardingError,
    generate_openclaw_commands,
    init_config,
    smoke_plan,
)
from helpers import init_git_repo


def test_init_config_creates_yaml_with_detected_repo_and_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_git_repo(tmp_path / "repo")
    config = tmp_path / "patchrelay.yaml"
    monkeypatch.chdir(repo)
    monkeypatch.setattr("patchrelay.onboarding.generate_token", lambda: "generated-token")

    result = init_config(config)

    assert result.config_path == config
    assert result.overwritten is False
    assert result.settings.repo.path == repo
    assert result.settings.repo.base_branch == "main"
    assert result.settings.server.token == "generated-token"
    assert "generated-token" in config.read_text(encoding="utf-8")


def test_init_config_refuses_existing_file_without_force(tmp_path: Path) -> None:
    config = tmp_path / "patchrelay.yaml"
    config.write_text("server:\n  token: old\n", encoding="utf-8")

    with pytest.raises(OnboardingError):
        init_config(config)


def test_init_config_force_overwrites_existing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = init_git_repo(tmp_path / "repo")
    config = tmp_path / "patchrelay.yaml"
    config.write_text("server:\n  token: old\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.setattr("patchrelay.onboarding.generate_token", lambda: "new-token")

    result = init_config(config, force=True)

    assert result.overwritten is True
    assert "new-token" in config.read_text(encoding="utf-8")


def test_smoke_plan_uses_small_fake_task() -> None:
    plan = smoke_plan("fake")

    assert plan.worker == "fake"
    assert "fake-change.txt" in plan.instruction


def test_generate_openclaw_commands_uses_config_values(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins" / "openclaw"
    settings = Settings(server=ServerConfig(host="127.0.0.1", port=8787, token="secret-token"))

    commands = generate_openclaw_commands(settings, plugin_root=plugin_root)
    joined = "\n".join(commands)

    assert "npm run plugin:validate" in joined
    assert "openclaw plugins install" in joined
    assert "http://127.0.0.1:8787" in joined
    assert "secret-token" in joined
