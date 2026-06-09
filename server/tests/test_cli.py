from pathlib import Path

import pytest

from patchrelay import cli
from patchrelay.config import RepoConfig, Settings, WorkerConfig
from helpers import init_git_repo


def test_doctor_reports_repo_and_profiles(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(
        repo=RepoConfig(path=repo, base_branch="main"),
        worker=WorkerConfig(codex_command="python", claude_command="python"),
    )

    result = cli.run_doctor(settings)

    assert any(check["name"] == "repo" and check["ok"] for check in result["checks"])
    assert any(check["name"] == "tests" and check["ok"] for check in result["checks"])


def test_request_json_uses_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"tasks": []}

    def fake_request(method: str, url: str, headers: dict[str, str], timeout: int) -> FakeResponse:
        captured.update({"method": method, "url": url, "headers": headers, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(cli.httpx, "request", fake_request)
    args = cli.build_parser().parse_args(["tasks", "--url", "http://example.test", "--token", "secret"])

    payload = cli.request_json(args, "GET", "/tasks")

    assert payload == {"tasks": []}
    assert captured["url"] == "http://example.test/tasks"
    assert captured["headers"] == {"Authorization": "Bearer secret"}


def test_tasks_parser_accepts_json_flag() -> None:
    args = cli.build_parser().parse_args(["tasks", "--json"])

    assert args.command == "tasks"
    assert args.json is True


def test_cancel_parser_requires_task_id() -> None:
    args = cli.build_parser().parse_args(["cancel", "task-1"])

    assert args.command == "cancel"
    assert args.task_id == "task-1"
