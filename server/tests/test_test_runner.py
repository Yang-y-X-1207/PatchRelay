import sys
from pathlib import Path

from patchrelay.config import TestProfile as PatchRelayTestProfile
from patchrelay.test_runner import TestRunner as PatchRelayTestRunner


def test_test_runner_handles_large_output_without_pipe_deadlock(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stdout.write('x' * 200000); sys.stderr.write('y' * 200000); sys.exit(3)",
    ]

    result = PatchRelayTestRunner(timeout_seconds=3).run(
        "large-output",
        PatchRelayTestProfile(command=command),
        tmp_path,
    )

    assert result.exit_code == 3
    assert result.timed_out is False
    assert len(result.stdout) == 200000
    assert len(result.stderr) == 200000
