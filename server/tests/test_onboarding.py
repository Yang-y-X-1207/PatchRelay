import json
import subprocess
from pathlib import Path

import pytest

from patchrelay.config import ServerConfig, Settings
from patchrelay.onboarding import (
    OnboardingError,
    OpenClawApplyStep,
    apply_openclaw_config,
    build_config_repair_plan,
    build_openclaw_apply_steps,
    generate_openclaw_commands,
    init_config,
    preview_setup,
    repair_config,
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


def test_repair_config_creates_missing_config_without_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = init_git_repo(tmp_path / "repo")
    config = tmp_path / "patchrelay.yaml"
    monkeypatch.chdir(repo)
    monkeypatch.setattr("patchrelay.onboarding.generate_token", lambda: "repair-token")

    plan = repair_config(config)

    assert plan.ok is True
    assert plan.changed is True
    assert plan.applied is False
    assert plan.actions[0].kind == "create"
    assert plan.data is not None
    assert plan.data["server"]["token"] == "repair-token"
    assert not config.exists()


def test_repair_config_apply_writes_missing_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = init_git_repo(tmp_path / "repo")
    config = tmp_path / "patchrelay.yaml"
    monkeypatch.chdir(repo)
    monkeypatch.setattr("patchrelay.onboarding.generate_token", lambda: "repair-token")

    plan = repair_config(config, apply=True)

    assert plan.ok is True
    assert plan.applied is True
    assert config.exists()
    assert "repair-token" in config.read_text(encoding="utf-8")


def test_repair_config_repairs_common_invalid_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = init_git_repo(tmp_path / "repo")
    config = tmp_path / "patchrelay.yaml"
    config.write_text(
        """
server:
  host: ""
  port: 0
  token: change-me
repo:
  path: C:/missing/repo
  base_branch: missing
  state_dir: ""
worker:
  default: unknown
  codex_command: []
tests:
  default:
    command: "python -m pytest"
limits:
  max_log_bytes: 0
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(repo)
    monkeypatch.setattr("patchrelay.onboarding.generate_token", lambda: "new-token")
    monkeypatch.setattr("patchrelay.onboarding.detect_default_worker", lambda: "fake")

    plan = build_config_repair_plan(config)

    assert plan.ok is True
    assert plan.data is not None
    assert plan.data["server"]["host"] == "127.0.0.1"
    assert plan.data["server"]["port"] == 8787
    assert plan.data["server"]["token"] == "new-token"
    assert plan.data["repo"]["path"] == str(repo)
    assert plan.data["repo"]["base_branch"] == "main"
    assert plan.data["repo"]["state_dir"] == ".patchrelay"
    assert plan.data["worker"]["default"] == "fake"
    assert plan.data["worker"]["codex_command"] == "codex"
    assert plan.data["tests"]["default"]["command"] == ["python", "-m", "pytest"]
    assert plan.data["limits"]["max_log_bytes"] == 1_048_576
    assert plan.data["limits"]["max_diff_bytes"] == 5_242_880
    assert plan.data["limits"]["task_timeout_seconds"] == 3_600
    assert {action.target for action in plan.actions} >= {
        "server.token",
        "repo.path",
        "repo.base_branch",
        "worker.default",
        "tests.default.command",
    }


def test_repair_config_reports_invalid_yaml(tmp_path: Path) -> None:
    config = tmp_path / "patchrelay.yaml"
    config.write_text("server:\n  token: [unterminated\n", encoding="utf-8")

    plan = repair_config(config, apply=True)

    assert plan.ok is False
    assert plan.applied is False
    assert "Invalid YAML" in plan.errors[0]


def test_repair_config_keeps_valid_config_unchanged(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    config = tmp_path / "patchrelay.yaml"
    init_config(config, repo_path=repo, token="valid-token")
    before = config.read_text(encoding="utf-8")

    plan = repair_config(config, apply=True)

    assert plan.ok is True
    assert plan.changed is False
    assert plan.applied is False
    assert config.read_text(encoding="utf-8") == before


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
    assert "openclaw skills install" in joined
    assert "skills:" in joined
    assert "http://127.0.0.1:8787" in joined
    assert "secret-token" in joined


def test_patchrelay_openclaw_skill_declares_delegate_boundaries() -> None:
    skill_path = Path(__file__).resolve().parents[2] / "plugins" / "openclaw" / "skills" / "patchrelay" / "SKILL.md"

    skill = skill_path.read_text(encoding="utf-8")

    assert "patchrelay_submit_task" in skill
    assert "not for read-only lookup or trivial one-line edits" in skill
    assert "skills.entries.patchrelay.enabled" in skill
    assert "plugins.entries.patchrelay.enabled" in skill


def test_build_openclaw_apply_steps_uses_structured_commands(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins" / "openclaw"
    settings = Settings(server=ServerConfig(host="127.0.0.1", port=8787, token="secret-token"))

    steps = build_openclaw_apply_steps(settings, plugin_root=plugin_root)

    assert [step.name for step in steps] == [
        "validate plugin",
        "install plugin",
        "configure plugin",
        "install skill",
        "enable skill",
    ]
    assert steps[0].cwd == plugin_root
    assert "plugin:validate" in steps[0].command
    assert steps[1].command[:3] == ["openclaw", "plugins", "install"]
    assert steps[2].stdin is not None
    assert "secret-token" in steps[2].stdin
    assert steps[3].command[:3] == ["openclaw", "skills", "install"]
    assert str(plugin_root / "skills" / "patchrelay") in steps[3].command
    assert "--global" in steps[3].command
    assert steps[4].stdin is not None
    assert "skills" in steps[4].stdin
    assert "patchrelay: { enabled: true }" in steps[4].stdin


def test_apply_openclaw_config_falls_back_after_size_drop_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        json.dumps({"plugins": {"entries": {"existing": {"enabled": True}}}}),
        encoding="utf-8",
    )
    settings = Settings(server=ServerConfig(host="127.0.0.1", port=8787, token="secret-token"))

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command == ["openclaw", "config", "patch", "--stdin"]:
            return subprocess.CompletedProcess(
                command,
                1,
                "",
                "Config write rejected: openclaw.json (size-drop:100->50).",
            )
        if command == ["openclaw", "config", "file"]:
            return subprocess.CompletedProcess(command, 0, str(config_path), "")
        if command == ["openclaw", "config", "validate"]:
            return subprocess.CompletedProcess(command, 0, "Config valid\n", "")
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    monkeypatch.setattr("patchrelay.onboarding.subprocess.run", fake_run)

    results = apply_openclaw_config(settings, plugin_root=tmp_path / "plugins" / "openclaw")

    assert [result.ok for result in results] == [True, True, True, True, True]
    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert updated["plugins"]["entries"]["existing"]["enabled"] is True
    assert updated["plugins"]["entries"]["patchrelay"]["config"]["token"] == "secret-token"
    assert updated["skills"]["entries"]["patchrelay"]["enabled"] is True


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
