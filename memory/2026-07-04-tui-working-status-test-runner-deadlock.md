# PatchRelay TUI Working Status Investigation

Date: 2026-07-04

## Symptom

The TUI kept showing a task as `working` even after the worker had completed the requested action.

## Root Cause

The task was not stale in the TUI. `/tasks` still returned `status=working` and `phase=tests`.
The worker had exited successfully, but the post-worker test process was still running:

- Task: `8e5e73675f614e65b8b8310a8b701386`
- Last event: `Running test profile 'default'.`
- Child process: `python -m pytest`

`TestRunner.run()` started test subprocesses with `stdout=PIPE` and `stderr=PIPE`, but did not read either pipe until the process exited. When the configured test command produced large pytest collection/import-error output, the child process filled the pipe buffer and blocked while writing output. The parent kept waiting for process exit, so PatchRelay never reached the final completed/failed state.

The local `patchrelay.yaml` also used `python -m pytest` from the repository root. For this repo the Python project is under `server/`, and a fresh worktree needs dev/TUI extras. The incorrect command produced dependency import errors, which triggered the pipe blockage.

## Fix

- `server/src/patchrelay/test_runner.py`
  - Capture stdout/stderr into temporary files instead of pipes.
  - Preserve cancel and timeout handling.
  - Ensure the process is waited/killed after cancellation or timeout.

- `server/tests/test_test_runner.py`
  - Added a regression test that writes 200 KB to stdout and stderr and exits with code 3. The old pipe-based runner would time out; the fixed runner returns the real exit code.

- `server/patchrelay.yaml`
  - Updated the local default test command to:
    `uv --project server run --extra dev --extra tui pytest -c server/pyproject.toml`

## Follow-up Finding

After the pipe deadlock fix, a later Claude task no longer stayed `working`; the API showed it as `failed`.
The worker had completed successfully, but the test profile failed because pytest was launched from the worktree root and did not read `server/pyproject.toml`. Without that pytest config, async worker tests were not handled with `asyncio_mode=auto`.

Adding `-c server/pyproject.toml` makes pytest use the server project configuration even though PatchRelay runs the command from the worktree root.

There was also a UI semantics issue: after the agent/worker exits, PatchRelay still uses `status=working` while it runs tests and artifact collection. That status is correct for the full PatchRelay pipeline but misleading in the TUI because it looks like the agent is still working. The TUI now displays derived labels:

- `working` + `phase=tests` -> `testing`
- `working` + `phase=artifacts` -> `finalizing`
- terminal statuses remain unchanged

## Evidence

- Current stuck task showed `working/tests` via API, so the TUI was reflecting server state.
- Manual reproduction with bad pytest command now returns instead of hanging:
  - `exit_code=2`
  - `timed_out=False`
  - `duration=1.91s`
  - `stdout_len=8199`
- Corrected worktree collect command returns:
  - `exit_code=0`
  - `timed_out=False`
  - `duration=2.61s`
- Corrected full worktree test command returns:
  - `124 passed`
  - `duration=58.44s`
- TUI display regression test verifies `working/tests` renders as `testing` and `working/artifacts` renders as `finalizing`.

## Verification

- `uv run pytest tests/test_test_runner.py tests/test_tasks.py`: 16 passed
- `uv run pytest`: 128 passed

## Status

DONE_WITH_CONCERNS

The code and config are fixed. Any already-running PatchRelay server must be restarted to pick up the new TestRunner and test command. The currently stuck old test process belongs to the old server process and will not be repaired in place.
