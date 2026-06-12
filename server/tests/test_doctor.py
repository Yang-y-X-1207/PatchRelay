from pathlib import Path

from patchrelay.config import RepoConfig, Settings, WorkerConfig
from patchrelay.doctor import config_error_result, run_doctor
from helpers import init_git_repo


def test_doctor_includes_hint_for_missing_base_branch(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(
        repo=RepoConfig(path=repo, base_branch="missing"),
        worker=WorkerConfig(codex_command="python", claude_command="python"),
    )

    result = run_doctor(settings)
    repo_check = next(check for check in result["checks"] if check["name"] == "repo")

    assert result["ok"] is False
    assert repo_check["ok"] is False
    assert "Base branch 'missing' does not exist" in repo_check["hint"]
    assert "main" in repo_check["hint"]


def test_config_error_result_includes_hint() -> None:
    result = config_error_result("invalid yaml")
    check = result["checks"][0]

    assert result["ok"] is False
    assert check["name"] == "config"
    assert check["hint"]
