from pathlib import Path
import asyncio
import sys

import psutil

from patchrelay.config import LimitsConfig, Settings, WorkerConfig
from patchrelay.workers import FakeWorkerAdapter, ProcessWorkerAdapter, WorkerRegistry, resolve_command_path


async def test_fake_worker_writes_file(tmp_path: Path) -> None:
    result = await FakeWorkerAdapter().run("make change", tmp_path, asyncio.Event())

    assert result.exit_code == 0
    assert (tmp_path / "fake-change.txt").read_text(encoding="utf-8").startswith(
        "PatchRelay fake worker instruction"
    )


async def test_fake_worker_can_fail(tmp_path: Path) -> None:
    result = await FakeWorkerAdapter().run("please fail", tmp_path, asyncio.Event())

    assert result.exit_code == 1
    assert "failure requested" in result.stderr


async def test_codex_worker_uses_configured_command(tmp_path: Path) -> None:
    command = create_python_worker(tmp_path, "codex-out")
    settings = Settings(
        worker=WorkerConfig(default="codex", codex_command=[sys.executable, str(command)]),
        limits=LimitsConfig(task_timeout_seconds=5),
    )

    result = await WorkerRegistry(settings).select("codex").run("hello", tmp_path, asyncio.Event())

    assert result.worker == "codex"
    assert result.exit_code == 0
    assert "codex-out" in result.stdout
    assert "exec --json --dangerously-bypass-approvals-and-sandbox hello" in result.stdout


async def test_claude_worker_uses_configured_command(tmp_path: Path) -> None:
    command = create_python_worker(tmp_path, "claude-out")
    settings = Settings(
        worker=WorkerConfig(default="claude", claude_command=[sys.executable, str(command)]),
        limits=LimitsConfig(task_timeout_seconds=5),
    )

    result = await WorkerRegistry(settings).select("claude").run("hello", tmp_path, asyncio.Event())

    assert result.worker == "claude"
    assert result.exit_code == 0
    assert "claude-out" in result.stdout
    assert (
        "-p --output-format json --dangerously-skip-permissions "
        "--disable-slash-commands --no-session-persistence hello"
    ) in result.stdout


def test_resolve_command_path_uses_path_shim(monkeypatch) -> None:
    monkeypatch.setattr("patchrelay.workers.shutil.which", lambda executable: f"C:/tools/{executable}.CMD")

    command = resolve_command_path(["claude", "-p"])

    assert command == ["C:/tools/claude.CMD", "-p"]


async def test_process_worker_can_be_canceled(tmp_path: Path) -> None:
    script = tmp_path / "sleep_worker.py"
    child_marker = tmp_path / "child.pid"
    script.write_text(
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        f"open({str(child_marker)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    cancel_event = asyncio.Event()
    adapter = ProcessWorkerAdapter("test", [sys.executable, str(script)], timeout_seconds=30)
    task = asyncio.create_task(adapter.run("ignored", tmp_path, cancel_event))

    deadline = asyncio.get_running_loop().time() + 5
    while not child_marker.exists() and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.05)
    assert child_marker.exists()
    child_pid = int(child_marker.read_text(encoding="utf-8"))

    cancel_event.set()
    result = await asyncio.wait_for(task, timeout=10)

    assert result.canceled is True
    assert result.exit_code == 130
    assert not psutil.pid_exists(child_pid)


def create_python_worker(tmp_path: Path, label: str) -> Path:
    script = tmp_path / f"{label}.py"
    script.write_text(
        "import sys\n"
        f"print({label!r}, ' '.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    return script
