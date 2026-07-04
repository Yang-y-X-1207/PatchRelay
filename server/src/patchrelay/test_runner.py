from __future__ import annotations

import asyncio
import contextlib
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from patchrelay.config import TestProfile
from patchrelay.workers import terminate_process_tree


@dataclass(frozen=True)
class TestRunResult:
    profile: str
    command: list[str]
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    timed_out: bool = False

    @property
    def status(self) -> str:
        if self.timed_out:
            return "timeout"
        return "passed" if self.exit_code == 0 else "failed"


class TestRunner:
    def __init__(self, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        profile_name: str,
        profile: TestProfile,
        cwd: Path,
        cancel_event: asyncio.Event | None = None,
    ) -> TestRunResult:
        started = time.monotonic()
        try:
            with (
                tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as stdout_file,
                tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as stderr_file,
            ):
                process = subprocess.Popen(
                    profile.command,
                    cwd=str(cwd),
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                while process.poll() is None:
                    if cancel_event is not None and cancel_event.is_set():
                        terminate_process_tree(process.pid)
                        wait_for_process_exit(process)
                        stdout, stderr = read_process_output(stdout_file, stderr_file)
                        duration = time.monotonic() - started
                        return TestRunResult(
                            profile=profile_name,
                            command=profile.command,
                            stdout=stdout,
                            stderr=(stderr + "\nTest canceled.").strip(),
                            exit_code=130,
                            duration_seconds=duration,
                        )
                    if time.monotonic() - started > self.timeout_seconds:
                        terminate_process_tree(process.pid)
                        wait_for_process_exit(process)
                        stdout, stderr = read_process_output(stdout_file, stderr_file)
                        duration = time.monotonic() - started
                        return TestRunResult(
                            profile=profile_name,
                            command=profile.command,
                            stdout=stdout,
                            stderr=(stderr + f"\nTest timed out after {self.timeout_seconds} seconds.").strip(),
                            exit_code=-1,
                            duration_seconds=duration,
                            timed_out=True,
                        )
                    time.sleep(0.05)
                wait_for_process_exit(process)
                stdout, stderr = read_process_output(stdout_file, stderr_file)
                duration = time.monotonic() - started
                return TestRunResult(
                    profile=profile_name,
                    command=profile.command,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=process.returncode or 0,
                    duration_seconds=duration,
                )
        except FileNotFoundError as exc:
            duration = time.monotonic() - started
            return TestRunResult(
                profile=profile_name,
                command=profile.command,
                stdout="",
                stderr=str(exc),
                exit_code=127,
                duration_seconds=duration,
            )


def read_process_output(stdout_file: TextIO, stderr_file: TextIO) -> tuple[str, str]:
    stdout_file.seek(0)
    stderr_file.seek(0)
    return stdout_file.read(), stderr_file.read()


def wait_for_process_exit(process: subprocess.Popen[str]) -> None:
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            process.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
