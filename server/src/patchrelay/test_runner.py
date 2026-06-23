from __future__ import annotations

import asyncio
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

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
            process = subprocess.Popen(
                profile.command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    terminate_process_tree(process.pid)
                    stdout, stderr = process.communicate()
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
                    stdout, stderr = process.communicate()
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
            stdout, stderr = process.communicate()
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
