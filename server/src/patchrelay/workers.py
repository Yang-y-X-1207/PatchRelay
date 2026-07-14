from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import subprocess
import threading
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
    timed_out: bool = False

    @property
    def failed(self) -> bool:
        return self.exit_code != 0


class WorkerAdapter(Protocol):
    name: str

    async def run(
        self,
        instruction: str,
        cwd: Path,
        cancel_event: asyncio.Event,
        env: dict[str, str] | None = None,
    ) -> WorkerResult:
        pass


class FakeWorkerAdapter:
    name = "fake"

    async def run(
        self,
        instruction: str,
        cwd: Path,
        cancel_event: asyncio.Event,
        env: dict[str, str] | None = None,
    ) -> WorkerResult:
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

    async def run(
        self,
        instruction: str,
        cwd: Path,
        cancel_event: asyncio.Event,
        env: dict[str, str] | None = None,
    ) -> WorkerResult:
        return await asyncio.to_thread(self._run_blocking, instruction, cwd, cancel_event, env)

    def _run_blocking(
        self,
        instruction: str,
        cwd: Path,
        cancel_event: asyncio.Event,
        env: dict[str, str] | None = None,
    ) -> WorkerResult:
        command = [*self._command, instruction]
        # Start from the parent environment so the worker keeps PATH etc., then
        # layer in any PatchRelay context vars (URL/token/task id/depth) so the
        # worker knows it is running inside PatchRelay and can request a handoff.
        process_env = None
        if env:
            process_env = os.environ.copy()
            process_env.update(env)
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=process_env,
                stdin=subprocess.DEVNULL,  # close stdin so workers like Codex don't block waiting for input
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            # Drain stdout and stderr in background threads to prevent pipe-buffer
            # deadlock. Workers like Codex emit a continuous stream of JSON events
            # throughout their run; if we only read after the process exits the
            # ~64 KB OS pipe buffer fills up and the worker blocks forever waiting
            # for a reader — while we wait for the worker to exit. Reading in
            # parallel threads breaks that deadlock.
            stdout_chunks: list[str] = []
            stderr_chunks: list[str] = []

            def _drain(pipe, chunks: list[str]) -> None:
                with contextlib.suppress(Exception):
                    for line in pipe:
                        chunks.append(line)

            t_out = threading.Thread(target=_drain, args=(process.stdout, stdout_chunks), daemon=True)
            t_err = threading.Thread(target=_drain, args=(process.stderr, stderr_chunks), daemon=True)
            t_out.start()
            t_err.start()

            started = time.monotonic()
            while process.poll() is None:
                if cancel_event.is_set():
                    terminate_process_tree(process.pid)
                    t_out.join(timeout=5)
                    t_err.join(timeout=5)
                    return WorkerResult(
                        worker=self.name,
                        stdout="".join(stdout_chunks),
                        stderr=("".join(stderr_chunks) + "\nWorker canceled.").strip(),
                        exit_code=130,
                        canceled=True,
                    )
                if time.monotonic() - started > self._timeout_seconds:
                    terminate_process_tree(process.pid)
                    t_out.join(timeout=5)
                    t_err.join(timeout=5)
                    return WorkerResult(
                        worker=self.name,
                        stdout="".join(stdout_chunks),
                        stderr=("".join(stderr_chunks) + f"\nWorker timed out after {self._timeout_seconds} seconds.").strip(),
                        exit_code=124,
                        timed_out=True,
                    )
                time.sleep(0.05)

            t_out.join(timeout=10)
            t_err.join(timeout=10)
            return WorkerResult(
                worker=self.name,
                stdout="".join(stdout_chunks),
                stderr="".join(stderr_chunks),
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
                [
                    *command_to_argv(self._settings.worker.codex_command),
                    "exec",
                    "--json",
                    # PatchRelay provides git-worktree isolation as the external
                    # sandbox, so we skip Codex's own interactive approval prompts.
                    # Without this flag Codex blocks forever waiting for user input.
                    "--dangerously-bypass-approvals-and-sandbox",
                ],
                self._settings.limits.worker_timeout_seconds,
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
                self._settings.limits.worker_timeout_seconds,
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
