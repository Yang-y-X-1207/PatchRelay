from pathlib import Path
import sys

from patchrelay.config import LimitsConfig, Settings, WorkerConfig
from patchrelay.workers import FakeWorkerAdapter, WorkerRegistry


async def test_fake_worker_writes_file(tmp_path: Path) -> None:
    result = await FakeWorkerAdapter().run("make change", tmp_path)

    assert result.exit_code == 0
    assert (tmp_path / "fake-change.txt").read_text(encoding="utf-8").startswith(
        "PatchRelay fake worker instruction"
    )


async def test_fake_worker_can_fail(tmp_path: Path) -> None:
    result = await FakeWorkerAdapter().run("please fail", tmp_path)

    assert result.exit_code == 1
    assert "failure requested" in result.stderr


async def test_codex_worker_uses_configured_command(tmp_path: Path) -> None:
    command = create_python_worker(tmp_path, "codex-out")
    settings = Settings(
        worker=WorkerConfig(default="codex", codex_command=[sys.executable, str(command)]),
        limits=LimitsConfig(task_timeout_seconds=5),
    )

    result = await WorkerRegistry(settings).select("codex").run("hello", tmp_path)

    assert result.worker == "codex"
    assert result.exit_code == 0
    assert "codex-out" in result.stdout
    assert "exec --json hello" in result.stdout


async def test_claude_worker_uses_configured_command(tmp_path: Path) -> None:
    command = create_python_worker(tmp_path, "claude-out")
    settings = Settings(
        worker=WorkerConfig(default="claude", claude_command=[sys.executable, str(command)]),
        limits=LimitsConfig(task_timeout_seconds=5),
    )

    result = await WorkerRegistry(settings).select("claude").run("hello", tmp_path)

    assert result.worker == "claude"
    assert result.exit_code == 0
    assert "claude-out" in result.stdout
    assert "-p --output-format stream-json --verbose hello" in result.stdout


def create_python_worker(tmp_path: Path, label: str) -> Path:
    script = tmp_path / f"{label}.py"
    script.write_text(
        "import sys\n"
        f"print({label!r}, ' '.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    return script
