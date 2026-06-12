from pathlib import Path

import pytest

from patchrelay import cli
from patchrelay.config import RepoConfig, Settings, WorkerConfig
from patchrelay.doctor import run_doctor
from helpers import init_git_repo


def test_doctor_reports_repo_and_profiles(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(
        repo=RepoConfig(path=repo, base_branch="main"),
        worker=WorkerConfig(codex_command="python", claude_command="python"),
    )

    result = run_doctor(settings)

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
    args = cli.build_parser().parse_args(
        ["submit", "fix", "the", "bug", "--worker", "fake", "--wait", "--timeout", "10", "--interval", "0.1"]
    )

    assert args.command == "submit"
    assert args.instruction == ["fix", "the", "bug"]
    assert args.worker == "fake"
    assert args.wait is True
    assert args.timeout == 10
    assert args.interval == 0.1


def test_cleanup_parser_defaults_to_preview() -> None:
    args = cli.build_parser().parse_args(["cleanup", "--config", "demo.yaml"])

    assert args.command == "cleanup"
    assert args.config == "demo.yaml"
    assert args.force is False


def test_cleanup_parser_accepts_force_and_json() -> None:
    args = cli.build_parser().parse_args(["cleanup", "--force", "--json"])

    assert args.command == "cleanup"
    assert args.force is True
    assert args.json is True


def test_init_parser_accepts_force_and_config() -> None:
    args = cli.build_parser().parse_args(
        [
            "init",
            "--config",
            "local.yaml",
            "--force",
            "--yes",
            "--repo-path",
            "repo",
            "--base-branch",
            "trunk",
            "--worker",
            "codex",
            "--test-command",
            "uv run pytest",
            "--token",
            "secret",
        ]
    )

    assert args.command == "init"
    assert args.config == "local.yaml"
    assert args.force is True
    assert args.yes is True
    assert args.repo_path == "repo"
    assert args.base_branch == "trunk"
    assert args.worker == "codex"
    assert args.test_command == "uv run pytest"
    assert args.token == "secret"


def test_smoke_parser_accepts_worker_url_and_token() -> None:
    args = cli.build_parser().parse_args(
        ["smoke", "--worker", "fake", "--url", "http://example.test", "--token", "secret", "--timeout", "10"]
    )

    assert args.command == "smoke"
    assert args.worker == "fake"
    assert args.url == "http://example.test"
    assert args.token == "secret"
    assert args.timeout == 10


def test_openclaw_parser_accepts_config() -> None:
    args = cli.build_parser().parse_args(["openclaw", "apply", "--config", "local.yaml", "--apply"])

    assert args.command == "openclaw"
    assert args.action == "apply"
    assert args.config == "local.yaml"
    assert args.apply is True


def test_parse_test_command_uses_shell_like_splitting() -> None:
    assert cli.parse_test_command('python -m pytest "tests/unit suite"') == [
        "python",
        "-m",
        "pytest",
        "tests/unit suite",
    ]


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


def test_smoke_uses_generated_instruction_and_waits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "patchrelay.yaml"
    config.write_text(
        """
server:
  token: file-token
repo:
  path: .
""",
        encoding="utf-8",
    )
    captured = {}

    def fake_submit(args) -> dict:
        captured["submit"] = {
            "url": args.url,
            "token": args.token,
            "instruction": args.instruction,
            "worker": args.worker,
        }
        return {"taskId": "task-1", "status": "queued"}

    def fake_wait(args, task_id: str) -> dict:
        captured["wait"] = {"task_id": task_id, "timeout": args.timeout}
        return {
            "taskId": task_id,
            "status": "completed",
            "worker": args.worker,
            "artifacts": {
                "patchrelay.summary": {
                    "content": {
                        "changedFiles": ["fake-change.txt"],
                        "testStatus": "passed",
                    }
                }
            },
        }

    monkeypatch.setattr(cli, "submit_task", fake_submit)
    monkeypatch.setattr(cli, "wait_for_task", fake_wait)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "patchrelay",
            "smoke",
            "--config",
            str(config),
            "--worker",
            "fake",
            "--token",
            "override-token",
            "--timeout",
            "10",
        ],
    )
    cli.main()

    assert captured["submit"]["token"] == "override-token"
    assert captured["submit"]["worker"] == "fake"
    assert "smoke test" in captured["submit"]["instruction"][0].lower()
    assert captured["wait"] == {"task_id": "task-1", "timeout": 10}


def test_openclaw_apply_defaults_to_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    config = tmp_path / "patchrelay.yaml"
    config.write_text("server:\n  token: file-token\n", encoding="utf-8")
    called = False

    def fake_apply(settings):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(cli, "apply_openclaw_config", fake_apply)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["patchrelay", "openclaw", "apply", "--config", str(config)],
    )

    cli.main()

    output = capsys.readouterr().out
    assert "dry-run" in output
    assert "configure plugin" in output
    assert called is False


def test_openclaw_apply_executes_when_apply_flag_is_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    config = tmp_path / "patchrelay.yaml"
    config.write_text("server:\n  token: file-token\n", encoding="utf-8")

    class Step:
        name = "configure plugin"
        cwd = None

        def display_command(self) -> str:
            return "openclaw config patch --stdin"

    class Result:
        step = Step()
        ok = True
        stdout = "done"
        stderr = ""

    monkeypatch.setattr(cli, "apply_openclaw_config", lambda settings: [Result()])
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["patchrelay", "openclaw", "apply", "--config", str(config), "--apply"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "[ok] configure plugin" in output
    assert "done" in output


def test_wait_for_task_stops_on_terminal_status(monkeypatch: pytest.MonkeyPatch) -> None:
    args = cli.build_parser().parse_args(["wait", "task-1", "--timeout", "1", "--interval", "0"])

    monkeypatch.setattr(
        cli,
        "request_json",
        lambda args, method, path, payload=None: {"taskId": "task-1", "status": "completed"},
    )

    payload = cli.wait_for_task(args, "task-1")

    assert payload["status"] == "completed"
