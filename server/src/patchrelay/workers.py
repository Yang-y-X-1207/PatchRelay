from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from patchrelay.config import Settings


WorkerName = Literal["auto", "codex", "claude", "fake"]


@dataclass(frozen=True)
class WorkerResult:
    worker: str
    stdout: str
    stderr: str
    exit_code: int

    @property
    def failed(self) -> bool:
        return self.exit_code != 0


class WorkerAdapter(Protocol):
    name: str

    async def run(self, instruction: str, cwd: Path) -> WorkerResult:
        pass


class FakeWorkerAdapter:
    name = "fake"

    async def run(self, instruction: str, cwd: Path) -> WorkerResult:
        await asyncio.sleep(0.05)
        output_path = cwd / "fake-change.txt"
        output_path.write_text(f"PatchRelay fake worker instruction:\n{instruction}\n", encoding="utf-8")
        if "fail" in instruction.lower():
            return WorkerResult(
                worker=self.name,
                stdout="",
                stderr="Fake worker failure requested by instruction.",
                exit_code=1,
            )
        return WorkerResult(worker=self.name, stdout="Fake worker completed.", stderr="", exit_code=0)


class ProcessWorkerAdapter:
    def __init__(self, name: str, command: list[str], timeout_seconds: int) -> None:
        self.name = name
        self._command = command
        self._timeout_seconds = timeout_seconds

    async def run(self, instruction: str, cwd: Path) -> WorkerResult:
        return await asyncio.to_thread(self._run_blocking, instruction, cwd)

    def _run_blocking(self, instruction: str, cwd: Path) -> WorkerResult:
        command = [*self._command, instruction]
        try:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout_seconds,
            )
            return WorkerResult(
                worker=self.name,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )
        except FileNotFoundError as exc:
            return WorkerResult(worker=self.name, stdout="", stderr=str(exc), exit_code=127)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return WorkerResult(
                worker=self.name,
                stdout=stdout,
                stderr=f"{stderr}\nWorker timed out after {self._timeout_seconds} seconds.".strip(),
                exit_code=124,
            )


class WorkerRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def select(self, requested: WorkerName) -> WorkerAdapter:
        selected = self._settings.worker.default if requested == "auto" else requested
        if selected == "auto":
            selected = "fake"
        if selected == "fake":
            return FakeWorkerAdapter()
        if selected == "codex":
            return ProcessWorkerAdapter(
                "codex",
                [*command_to_argv(self._settings.worker.codex_command), "exec", "--json"],
                self._settings.limits.task_timeout_seconds,
            )
        if selected == "claude":
            return ProcessWorkerAdapter(
                "claude",
                [
                    *command_to_argv(self._settings.worker.claude_command),
                    "-p",
                    "--output-format",
                    "stream-json",
                    "--verbose",
                ],
                self._settings.limits.task_timeout_seconds,
            )
        raise ValueError(f"Unsupported worker: {selected}")


def command_to_argv(command: str | list[str]) -> list[str]:
    return [command] if isinstance(command, str) else command
