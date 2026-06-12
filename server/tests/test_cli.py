from pathlib import Path

import pytest

from patchrelay import cli
from patchrelay.config import ConfigError, RepoConfig, Settings, WorkerConfig
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


def test_setup_parser_accepts_yes_no_flow_options() -> None:
    args = cli.build_parser().parse_args(
        [
            "setup",
            "--config",
            "local.yaml",
            "--force",
            "--yes",
            "--worker",
            "fake",
            "--gateway-url",
            "http://gateway.test",
            "--gateway-token",
            "gateway-secret",
            "--timeout",
            "10",
        ]
    )

    assert args.command == "setup"
    assert args.config == "local.yaml"
    assert args.force is True
    assert args.yes is True
    assert args.worker == "fake"
    assert args.gateway_url == "http://gateway.test"
    assert args.gateway_token == "gateway-secret"
    assert args.timeout == 10


def test_setup_status_parser_accepts_gateway_options() -> None:
    args = cli.build_parser().parse_args(
        [
            "setup",
            "status",
            "--config",
            "local.yaml",
            "--gateway-url",
            "http://gateway.test",
            "--gateway-token",
            "gateway-secret",
        ]
    )

    assert args.command == "setup"
    assert args.action == "status"
    assert args.config == "local.yaml"
    assert args.gateway_url == "http://gateway.test"
    assert args.gateway_token == "gateway-secret"


def test_smoke_parser_accepts_worker_url_and_token() -> None:
    args = cli.build_parser().parse_args(
        [
            "smoke",
            "--worker",
            "fake",
            "--via",
            "openclaw",
            "--url",
            "http://example.test",
            "--token",
            "secret",
            "--gateway-url",
            "http://gateway.test",
            "--gateway-token",
            "gateway-secret",
            "--timeout",
            "10",
        ]
    )

    assert args.command == "smoke"
    assert args.worker == "fake"
    assert args.via == "openclaw"
    assert args.url == "http://example.test"
    assert args.token == "secret"
    assert args.gateway_url == "http://gateway.test"
    assert args.gateway_token == "gateway-secret"
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


def test_ask_yes_no_reprompts_until_valid_answer(capsys) -> None:
    answers = iter(["maybe", ""])

    result = cli.ask_yes_no("Continue?", default=True, input_func=lambda prompt: next(answers))

    assert result is True
    assert "Please answer yes or no." in capsys.readouterr().out


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


def test_request_openclaw_json_invokes_gateway_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"result": {"taskId": "task-1", "status": "queued"}}

    def fake_request(
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict,
        timeout: int,
    ) -> FakeResponse:
        captured.update({"method": method, "url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(cli.httpx, "request", fake_request)
    args = cli.build_parser().parse_args(
        ["smoke", "--via", "openclaw", "--gateway-url", "http://gateway.test", "--gateway-token", "secret"]
    )

    payload = cli.request_openclaw_json(args, "patchrelay_get_task", {"taskId": "task-1"})

    assert payload == {"taskId": "task-1", "status": "queued"}
    assert captured["method"] == "POST"
    assert captured["url"] == "http://gateway.test/tools/invoke"
    assert captured["headers"] == {"Authorization": "Bearer secret"}
    assert captured["json"] == {"name": "patchrelay_get_task", "args": {"taskId": "task-1"}}


def test_unwrap_openclaw_payload_accepts_direct_and_wrapped_payloads() -> None:
    direct = {"taskId": "task-1", "status": "completed"}
    wrapped = {"result": {"taskId": "task-2", "status": "queued"}}

    assert cli.unwrap_openclaw_payload(direct) == direct
    assert cli.unwrap_openclaw_payload(wrapped) == {"taskId": "task-2", "status": "queued"}


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


def test_smoke_via_openclaw_uses_gateway_tools(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "patchrelay.yaml"
    config.write_text("server:\n  token: file-token\n", encoding="utf-8")
    captured = {}

    def fake_submit(args) -> dict:
        captured["submit"] = {
            "gateway_url": args.gateway_url,
            "gateway_token": args.gateway_token,
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

    monkeypatch.setattr(cli, "openclaw_submit_task", fake_submit)
    monkeypatch.setattr(cli, "wait_for_openclaw_task", fake_wait)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "patchrelay",
            "smoke",
            "--config",
            str(config),
            "--via",
            "openclaw",
            "--gateway-url",
            "http://gateway.test",
            "--gateway-token",
            "gateway-secret",
            "--timeout",
            "10",
        ],
    )

    cli.main()

    assert captured["submit"]["gateway_url"] == "http://gateway.test"
    assert captured["submit"]["gateway_token"] == "gateway-secret"
    assert captured["submit"]["worker"] == "fake"
    assert "smoke test" in captured["submit"]["instruction"].lower()
    assert captured["wait"] == {"task_id": "task-1", "timeout": 10}


def test_setup_stops_when_user_declines_existing_config(tmp_path: Path, capsys) -> None:
    config = tmp_path / "patchrelay.yaml"
    config.write_text("server:\n  token: existing\n", encoding="utf-8")
    args = cli.build_parser().parse_args(["setup", "--config", str(config)])

    cli.run_setup(args, input_func=lambda prompt: "n")

    assert "existing config kept" in capsys.readouterr().out
    assert "existing" in config.read_text(encoding="utf-8")


def test_setup_runs_yes_no_happy_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    config = tmp_path / "patchrelay.yaml"
    settings = Settings()
    init_result = type("InitResult", (), {"config_path": config, "settings": settings, "overwritten": False})()
    captured = {}
    answers = iter(["y", "y", "y", "n"])

    monkeypatch.setattr(cli, "init_config", lambda config_path, force: init_result)
    monkeypatch.setattr(
        cli,
        "preview_setup",
        lambda config_path, worker=None: type(
            "Preview",
            (),
            {
                "config_path": config,
                "repo_path": tmp_path,
                "base_branch": "main",
                "worker": worker or "fake",
                "test_command": ["python", "-m", "pytest"],
                "server_host": "127.0.0.1",
                "server_port": 8787,
            },
        )(),
    )
    monkeypatch.setattr(cli, "run_doctor", lambda settings: {"ok": True, "checks": []})
    monkeypatch.setattr(
        cli,
        "apply_openclaw_config",
        lambda settings: [
            type(
                "Result",
                (),
                {
                    "ok": True,
                    "stdout": "done",
                    "stderr": "",
                    "step": type(
                        "Step",
                        (),
                        {
                            "name": "configure plugin",
                            "display_command": lambda self: "openclaw config patch --stdin",
                        },
                    )(),
                },
            )()
        ],
    )

    def fake_smoke_plan(worker: str):
        captured["worker"] = worker
        return type("SmokePlan", (), {"instruction": "smoke", "worker": worker})()

    monkeypatch.setattr(cli, "smoke_plan", fake_smoke_plan)
    args = cli.build_parser().parse_args(["setup", "--config", str(config), "--worker", "fake"])

    cli.run_setup(args, input_func=lambda prompt: next(answers))

    output = capsys.readouterr().out
    assert "created:" in output
    assert "Detected setup defaults:" in output
    assert "[ok] configure plugin" in output
    assert "setup completed" in output
    assert "worker" not in captured


def test_setup_yes_accepts_default_answers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    config = tmp_path / "patchrelay.yaml"
    settings = Settings()
    init_result = type("InitResult", (), {"config_path": config, "settings": settings, "overwritten": False})()
    calls = {"doctor": 0, "apply": 0, "smoke": 0}

    monkeypatch.setattr(
        cli,
        "preview_setup",
        lambda config_path, worker=None: type(
            "Preview",
            (),
            {
                "config_path": config,
                "repo_path": tmp_path,
                "base_branch": "main",
                "worker": worker or "fake",
                "test_command": ["python", "-m", "pytest"],
                "server_host": "127.0.0.1",
                "server_port": 8787,
            },
        )(),
    )
    monkeypatch.setattr(cli, "init_config", lambda config_path, force: init_result)

    def fake_doctor(settings):
        calls["doctor"] += 1
        return {"ok": True, "checks": []}

    monkeypatch.setattr(cli, "run_doctor", fake_doctor)
    monkeypatch.setattr(cli, "apply_openclaw_config", lambda settings: calls.__setitem__("apply", 1) or [])
    monkeypatch.setattr(cli, "openclaw_submit_task", lambda args: calls.__setitem__("smoke", 1) or {"taskId": "task-1"})
    args = cli.build_parser().parse_args(["setup", "--config", str(config), "--yes"])

    cli.run_setup(args, input_func=lambda prompt: pytest.fail("input should not be called"))

    output = capsys.readouterr().out
    assert "Generate PatchRelay config" in output
    assert calls["doctor"] == 1
    assert calls["apply"] == 0
    assert calls["smoke"] == 0


def test_setup_status_reports_all_checks_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()

    monkeypatch.setattr(cli, "load_settings", lambda config: settings)
    monkeypatch.setattr(cli, "run_doctor", lambda settings: {"ok": True, "checks": []})
    monkeypatch.setattr(
        cli,
        "request_json",
        lambda args, method, path, payload=None: {"status": "ok"},
    )
    monkeypatch.setattr(cli, "request_openclaw_json", lambda args, tool_name, tool_args: {"error": "not found"})
    args = cli.build_parser().parse_args(["setup", "status"])

    result = cli.run_setup_status(args)

    assert result["ok"] is True
    assert [check["name"] for check in result["checks"]] == [
        "config",
        "doctor",
        "patchrelay_server",
        "openclaw_gateway",
    ]
    assert all(check["ok"] for check in result["checks"])


def test_setup_status_reports_config_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_load_settings(config: str) -> Settings:
        raise ConfigError("bad config")

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(
        cli,
        "request_openclaw_json",
        lambda args, tool_name, tool_args: (_ for _ in ()).throw(SystemExit("gateway down")),
    )
    args = cli.build_parser().parse_args(["setup", "status", "--config", "missing.yaml"])

    result = cli.run_setup_status(args)

    assert result["ok"] is False
    assert result["checks"][0]["name"] == "config"
    assert result["checks"][0]["ok"] is False
    assert result["checks"][1]["message"] == "skipped because config failed"


def test_print_setup_status_includes_hints(capsys) -> None:
    cli.print_setup_status(
        {
            "ok": False,
            "checks": [
                {
                    "name": "config",
                    "ok": False,
                    "message": "missing",
                    "hint": "run setup",
                }
            ],
        }
    )

    output = capsys.readouterr().out
    assert "[fail] config: missing" in output
    assert "hint: run setup" in output
    assert "overall: fail" in output


def test_extract_task_id_rejects_missing_task_id() -> None:
    with pytest.raises(SystemExit):
        cli.extract_task_id({"status": "queued"})


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
