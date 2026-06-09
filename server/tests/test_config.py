from pathlib import Path

import pytest

from patchrelay.config import ConfigError, load_settings


def test_load_settings_reads_yaml(tmp_path: Path) -> None:
    config = tmp_path / "patchrelay.yaml"
    config.write_text(
        """
server:
  token: test-token
repo:
  path: .
  base_branch: trunk
worker:
  default: codex
tests:
  default:
    command: ["python", "-m", "pytest"]
""",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.server.token == "test-token"
    assert settings.repo.base_branch == "trunk"
    assert settings.worker.default == "codex"


def test_load_settings_rejects_missing_default_test_profile(tmp_path: Path) -> None:
    config = tmp_path / "patchrelay.yaml"
    config.write_text(
        """
tests:
  unit:
    command: ["python", "-m", "pytest", "tests"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_settings(config)


def test_load_settings_uses_config_environment_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "env-config.yaml"
    config.write_text("server:\n  token: env-token\n", encoding="utf-8")
    monkeypatch.setenv("PATCHRELAY_CONFIG", str(config))

    settings = load_settings()

    assert settings.server.token == "env-token"
