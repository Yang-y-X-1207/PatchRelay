import sys
from pathlib import Path

import psutil

from patchrelay.config import RepoConfig, Settings, WorkerConfig
from patchrelay.runtime import (
    RuntimeManager,
    RuntimeOptions,
    managed_process_matches,
    parse_gateway_url,
    runtime_payload,
    with_windows_system_path,
    worker_readiness,
)
from helpers import init_git_repo


def test_parse_gateway_url_defaults_port() -> None:
    assert parse_gateway_url("http://127.0.0.1:19001") == {"host": "127.0.0.1", "port": 19001}
    assert parse_gateway_url("http://gateway.test") == {"host": "gateway.test", "port": 19001}


def test_runtime_payload_combines_services_and_workers(tmp_path: Path) -> None:
    payload = runtime_payload(
        "status",
        tmp_path / "runtime.json",
        [{"name": "patchrelay_server", "ok": True}],
        [{"name": "codex", "ok": False}],
    )

    assert payload["ok"] is False
    assert payload["statePath"].endswith("runtime.json")


def test_worker_readiness_reports_missing_command(monkeypatch) -> None:
    monkeypatch.setattr("patchrelay.runtime.shutil.which", lambda executable: None)

    result = worker_readiness("codex", ["codex"])

    assert result["ok"] is False
    assert result["status"] == "unavailable"
    assert "not found" in result["message"]


def test_worker_readiness_runs_version_check(tmp_path: Path, monkeypatch) -> None:
    script = tmp_path / "worker_version.py"
    script.write_text("print('worker 1.2.3')\n", encoding="utf-8")
    monkeypatch.setattr("patchrelay.runtime.shutil.which", lambda executable: sys.executable)

    result = worker_readiness("codex", ["python", str(script)])

    assert result["ok"] is True
    assert result["version"] == "worker 1.2.3"


def test_runtime_start_records_patchrelay_process_without_starting_openclaw(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        worker=WorkerConfig(codex_command=sys.executable, claude_command=sys.executable),
    )
    options = RuntimeOptions(
        config_path="local.yaml",
        gateway_url="http://127.0.0.1:19001",
        gateway_token="token",
        start_openclaw=False,
        check_workers=False,
        timeout_seconds=0,
    )
    launched = {}

    class Process:
        pid = 12345

    def fake_launch(command, cwd, env, log_path):
        launched.update({"command": command, "cwd": cwd, "env": env, "log_path": log_path})
        return Process()

    reachable = iter([False, True, True])
    monkeypatch.setattr("patchrelay.runtime.launch_background_process", fake_launch)
    monkeypatch.setattr(RuntimeManager, "_patchrelay_reachable", lambda self: next(reachable))
    monkeypatch.setattr("patchrelay.runtime.psutil.pid_exists", lambda pid: True)

    result = RuntimeManager(settings, options).start()

    assert result["ok"] is True
    assert result["services"][0]["status"] == "started"
    assert launched["env"]["PATCHRELAY_CONFIG"] == "local.yaml"
    assert "patchrelay.app:create_app" in launched["command"]
    assert (repo / ".patchrelay-test" / "runtime.json").exists()


def test_runtime_start_openclaw_uses_explicit_command_and_windows_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")))
    options = RuntimeOptions(
        config_path="local.yaml",
        gateway_url="http://127.0.0.1:19001",
        gateway_token="gateway-token",
        start_patchrelay=False,
        check_workers=False,
        timeout_seconds=0,
    )
    launched = {}

    class Process:
        pid = 23456

    def fake_launch(command, cwd, env, log_path):
        launched.update({"command": command, "cwd": cwd, "env": env, "log_path": log_path})
        return Process()

    reachable = iter([False, True, True])
    monkeypatch.setattr("patchrelay.runtime.shutil.which", lambda executable: r"D:\NodeJS\openclaw.ps1")
    monkeypatch.setattr("patchrelay.runtime.launch_background_process", fake_launch)
    monkeypatch.setattr("patchrelay.runtime.tcp_reachable", lambda host, port: next(reachable))
    monkeypatch.setattr("patchrelay.runtime.psutil.pid_exists", lambda pid: True)
    monkeypatch.setattr(
        "patchrelay.runtime.with_windows_system_path",
        lambda env: {**env, "Path": r"C:\Windows\System32;D:\NodeJS"},
    )

    result = RuntimeManager(settings, options).start()

    assert result["ok"] is True
    assert launched["command"] == [
        r"D:\NodeJS\openclaw.ps1",
        "gateway",
        "run",
        "--port",
        "19001",
        "--auth",
        "token",
        "--token",
        "gateway-token",
        "--bind",
        "loopback",
        "--force",
    ]
    assert launched["env"]["Path"].startswith(r"C:\Windows\System32")
    assert launched["env"]["OPENCLAW_SKIP_STARTUP_MODEL_PREWARM"] == "1"


def test_with_windows_system_path_adds_system_directories(monkeypatch) -> None:
    monkeypatch.setattr("patchrelay.runtime.os.name", "nt")

    result = with_windows_system_path(
        {
            "PATH": r"D:\NodeJS",
            "Path": r"C:\Existing",
            "SystemRoot": r"C:\Windows",
        }
    )

    assert "PATH" not in result
    assert result["Path"].split(";")[:3] == [
        r"C:\Windows\System32",
        r"C:\Windows\System32\Wbem",
        r"C:\Windows\System32\WindowsPowerShell\v1.0",
    ]
    assert result["Path"].endswith(r"C:\Existing")


def test_start_script_uses_current_dir_explicit_gateway_and_windows_path() -> None:
    script = Path(__file__).resolve().parents[1] / "start.ps1"
    text = script.read_text(encoding="utf-8")

    assert "$ServerDir = $PSScriptRoot" in text
    assert r"C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay-tui\server" not in text
    assert "Add-WindowsPathEntry (Join-Path $WindowsRoot \"System32\")" in text
    assert "Start-Process $PowerShellExe" in text
    assert "OPENCLAW_SKIP_STARTUP_MODEL_PREWARM" in text
    assert (
        "openclaw gateway run --port 19001 --auth token --token openclaw-local-token --bind loopback --force"
        in text
    )


def test_runtime_stop_terminates_managed_process(tmp_path: Path, monkeypatch) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")))
    options = RuntimeOptions(
        config_path="local.yaml",
        gateway_url="http://127.0.0.1:19001",
        gateway_token="token",
    )
    manager = RuntimeManager(settings, options)
    manager.state_dir.mkdir(parents=True)
    manager.state_path.write_text(
        '{"patchrelay_server": {"pid": 123, "command": [], "logPath": "", "url": "http://127.0.0.1:8787"}}',
        encoding="utf-8",
    )
    stopped = []

    monkeypatch.setattr("patchrelay.runtime.psutil.pid_exists", lambda pid: pid == 123 and not stopped)
    monkeypatch.setattr("patchrelay.runtime.managed_process_matches", lambda pid, name: True)
    monkeypatch.setattr("patchrelay.runtime.terminate_process_tree", lambda pid: stopped.append(pid))

    result = manager.stop()

    assert result["ok"] is True
    assert result["services"][0]["status"] == "stopped"
    assert stopped == [123]


def test_runtime_status_can_skip_worker_checks(tmp_path: Path, monkeypatch) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")))
    options = RuntimeOptions(
        config_path="local.yaml",
        gateway_url="http://127.0.0.1:19001",
        gateway_token="token",
        check_workers=False,
    )

    monkeypatch.setattr(RuntimeManager, "_patchrelay_reachable", lambda self: False)
    monkeypatch.setattr("patchrelay.runtime.tcp_reachable", lambda host, port: False)

    result = RuntimeManager(settings, options).status()

    assert result["workers"] == []


def test_managed_process_matches_current_process_safely() -> None:
    current = psutil.Process().pid

    assert managed_process_matches(current, "unknown") is False
