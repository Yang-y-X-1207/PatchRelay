from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from patchrelay.config import TestProfile


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

    def run(self, profile_name: str, profile: TestProfile, cwd: Path) -> TestRunResult:
        started = time.monotonic()
        try:
            result = subprocess.run(
                profile.command,
                cwd=str(cwd),
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
            duration = time.monotonic() - started
            return TestRunResult(
                profile=profile_name,
                command=profile.command,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - started
            return TestRunResult(
                profile=profile_name,
                command=profile.command,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                exit_code=-1,
                duration_seconds=duration,
                timed_out=True,
            )
