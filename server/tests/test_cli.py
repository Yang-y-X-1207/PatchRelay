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


def test_request_json_uses_bearer_token_and_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"tasks": []}

    def fake_request(
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict | None,
        timeout: int,
    ) -> FakeResponse:
        captured.update({"method": method, "url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(cli.httpx, "request", fake_request)
    args = cli.build_parser().parse_args(["tasks", "--url", "http://example.test", "--token", "secret"])

    payload = cli.request_json(args, "POST", "/tasks", {"hello": "world"})

    assert payload == {"tasks": []}
    assert captured["url"] == "http://example.test/tasks"
    assert captured["headers"] == {"Authorization": "Bearer secret"}
    assert captured["json"] == {"hello": "world"}


def test_tasks_parser_accepts_json_flag() -> None:
    args = cli.build_parser().parse_args(["tasks", "--json"])

    assert args.command == "tasks"
    assert args.json is True


def test_cancel_parser_requires_task_id() -> None:
    args = cli.build_parser().parse_args(["cancel", "task-1"])

    assert args.command == "cancel"
    assert args.task_id == "task-1"


def test_submit_parser_collects_instruction() -> None:
    args = cli.build_parser().parse_args(["submit", "fix", "the", "bug", "--worker", "fake", "--wait"])

    assert args.command == "submit"
    assert args.instruction == ["fix", "the", "bug"]
    assert args.worker == "fake"
    assert args.wait is True


def test_submit_task_sends_a2a_like_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_request_json(args, method: str, path: str, payload: dict | None = None) -> dict:
        captured.update({"method": method, "path": path, "payload": payload})
        return {"taskId": "task-1", "status": "queued"}

    monkeypatch.setattr(cli, "request_json", fake_request_json)
    args = cli.build_parser().parse_args(["submit", "fix", "bug", "--worker", "fake", "--test-profile", "default"])

    response = cli.submit_task(args)

    assert response["taskId"] == "task-1"
    assert captured["method"] == "POST"
    assert captured["path"] == "/message:send"
    assert captured["payload"]["message"]["parts"][0]["text"] == "fix bug"
    assert captured["payload"]["metadata"]["patchrelay"]["worker"] == "fake"


def test_wait_for_task_stops_on_terminal_status(monkeypatch: pytest.MonkeyPatch) -> None:
    args = cli.build_parser().parse_args(["wait", "task-1", "--timeout", "1", "--interval", "0"])

    monkeypatch.setattr(
        cli,
        "request_json",
        lambda args, method, path, payload=None: {"taskId": "task-1", "status": "completed"},
    )

    payload = cli.wait_for_task(args, "task-1")

    assert payload["status"] == "completed"
