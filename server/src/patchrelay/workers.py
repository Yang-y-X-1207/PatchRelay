from __future__ import annotations

import asyncio
import contextlib
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import psutil

from patchrelay.config import Settings


WorkerName = Literal["auto", "codex", "claude", "fake"]


@dataclass(frozen=True)
class WorkerResult:
    worker: str
    stdout: str
    stderr: str
    exit_code: int
    canceled: bool = False

    @property
    def failed(self) -> bool:
        return self.exit_code != 0


class WorkerAdapter(Protocol):
    name: str

    async def run(self, instruction: str, cwd: Path, cancel_event: asyncio.Event) -> WorkerResult:
        pass


class FakeWorkerAdapter:
    name = "fake"

    async def run(self, instruction: str, cwd: Path, cancel_event: asyncio.Event) -> WorkerResult:
        sleep_seconds = 1.0 if "sleep" in instruction.lower() else 0.05
        try:
            await asyncio.wait_for(cancel_event.wait(), timeout=sleep_seconds)
            return WorkerResult(worker=self.name, stdout="", stderr="Worker canceled.", exit_code=130, canceled=True)
        except asyncio.TimeoutError:
            pass
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
        self._command = resolve_command_path(command)
        self._timeout_seconds = timeout_seconds

    async def run(self, instruction: str, cwd: Path, cancel_event: asyncio.Event) -> WorkerResult:
        return await asyncio.to_thread(self._run_blocking, instruction, cwd, cancel_event)

    def _run_blocking(self, instruction: str, cwd: Path, cancel_event: asyncio.Event) -> WorkerResult:
        command = [*self._command, instruction]
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            started = time.monotonic()
            while process.poll() is None:
                if cancel_event.is_set():
                    terminate_process_tree(process.pid)
                    stdout, stderr = process.communicate()
                    return WorkerResult(
                        worker=self.name,
                        stdout=stdout,
                        stderr=(stderr + "\nWorker canceled.").strip(),
                        exit_code=130,
                        canceled=True,
                    )
                if time.monotonic() - started > self._timeout_seconds:
                    terminate_process_tree(process.pid)
                    stdout, stderr = process.communicate()
                    return WorkerResult(
                        worker=self.name,
                        stdout=stdout,
                        stderr=(stderr + f"\nWorker timed out after {self._timeout_seconds} seconds.").strip(),
                        exit_code=124,
                    )
                time.sleep(0.05)
            stdout, stderr = process.communicate()
            return WorkerResult(
                worker=self.name,
                stdout=stdout,
                stderr=stderr,
                exit_code=process.returncode or 0,
            )
        except FileNotFoundError as exc:
            return WorkerResult(worker=self.name, stdout="", stderr=str(exc), exit_code=127)


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
                    "json",
                    "--dangerously-skip-permissions",
                    "--disable-slash-commands",
                    "--no-session-persistence",
                ],
                self._settings.limits.task_timeout_seconds,
            )
        raise ValueError(f"Unsupported worker: {selected}")


def command_to_argv(command: str | list[str]) -> list[str]:
    return [command] if isinstance(command, str) else command


def resolve_command_path(command: list[str]) -> list[str]:
    if not command:
        return command
    executable = command[0]
    resolved = shutil.which(executable)
    if resolved is None:
        return command
    return [resolved, *command[1:]]


def worker_command_status(command: str | list[str]) -> dict[str, str | bool]:
    executable = command_to_argv(command)[0]
    resolved = shutil.which(executable)
    return {
        "configuredCommand": " ".join(command_to_argv(command)),
        "available": resolved is not None,
        "path": resolved or "",
    }


def terminate_process_tree(pid: int) -> None:
    with contextlib.suppress(psutil.NoSuchProcess):
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            with contextlib.suppress(psutil.NoSuchProcess):
                child.terminate()
        parent.terminate()
        gone, alive = psutil.wait_procs([*children, parent], timeout=3)
        for process in alive:
            with contextlib.suppress(psutil.NoSuchProcess):
                process.kill()
