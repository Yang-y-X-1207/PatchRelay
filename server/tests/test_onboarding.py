from pathlib import Path

import pytest

from patchrelay.config import ServerConfig, Settings
from patchrelay.onboarding import (
    OnboardingError,
    OpenClawApplyStep,
    apply_openclaw_config,
    build_openclaw_apply_steps,
    generate_openclaw_commands,
    init_config,
    preview_setup,
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


def test_init_config_accepts_scripted_overrides(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    config = tmp_path / "patchrelay.yaml"

    result = init_config(
        config,
        repo_path=repo,
        base_branch="main",
        worker="codex",
        test_command=["uv", "run", "pytest"],
        token="script-token",
    )

    assert result.settings.repo.path == repo
    assert result.settings.repo.base_branch == "main"
    assert result.settings.worker.default == "codex"
    assert result.settings.tests["default"].command == ["uv", "run", "pytest"]
    assert result.settings.server.token == "script-token"


def test_preview_setup_returns_detected_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = init_git_repo(tmp_path / "repo")
    monkeypatch.setattr("patchrelay.onboarding.detect_default_worker", lambda: "fake")

    preview = preview_setup(tmp_path / "patchrelay.yaml", repo_path=repo)

    assert preview.config_path == tmp_path / "patchrelay.yaml"
    assert preview.repo_path == repo
    assert preview.base_branch == "main"
    assert preview.worker == "fake"
    assert preview.test_command


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


def test_build_openclaw_apply_steps_uses_structured_commands(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins" / "openclaw"
    settings = Settings(server=ServerConfig(host="127.0.0.1", port=8787, token="secret-token"))

    steps = build_openclaw_apply_steps(settings, plugin_root=plugin_root)

    assert [step.name for step in steps] == ["validate plugin", "install plugin", "configure plugin"]
    assert steps[0].cwd == plugin_root
    assert "plugin:validate" in steps[0].command
    assert steps[1].command[:3] == ["openclaw", "plugins", "install"]
    assert steps[2].stdin is not None
    assert "secret-token" in steps[2].stdin


def test_apply_openclaw_config_stops_on_failed_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(server=ServerConfig(token="secret-token"))
    step = OpenClawApplyStep(name="fail", command=["missing"])
    calls = []

    def fake_steps(settings: Settings, plugin_root: Path | None = None) -> list[OpenClawApplyStep]:
        return [step, OpenClawApplyStep(name="skipped", command=["skipped"])]

    def fake_run(*args, **kwargs):
        calls.append(args[0])
        raise FileNotFoundError("missing")

    monkeypatch.setattr("patchrelay.onboarding.build_openclaw_apply_steps", fake_steps)
    monkeypatch.setattr("patchrelay.onboarding.subprocess.run", fake_run)

    results = apply_openclaw_config(settings, plugin_root=tmp_path)

    assert len(results) == 1
    assert results[0].exit_code == 127
    assert calls == [["missing"]]
