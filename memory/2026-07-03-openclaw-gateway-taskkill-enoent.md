# 2026-07-03 OpenClaw Gateway taskkill ENOENT

## Symptom

Starting the PatchRelay environment script opened the OpenClaw Gateway window, then OpenClaw logged:

```text
[gateway] startup model warmup timed out after 5000ms; continuing without waiting
Error: spawn taskkill ENOENT
```

The unhandled child process `error` event crashed the Gateway process on Windows.

## Root Cause

OpenClaw 2026.6.1 uses `spawn("taskkill", ...)` from its Windows process-tree cleanup path. If the Gateway process inherits a PATH that does not include `C:\Windows\System32`, Node cannot resolve `taskkill.exe` and emits `ENOENT`.

The PatchRelay `server/start.ps1` script also launched Gateway with the bare `openclaw gateway` command, so it relied entirely on inherited defaults and did not force the intended local Gateway port/auth/bind settings.

Confirmed with a minimal Node reproduction:

```text
PATH=D:\NodeJS              -> spawn taskkill => ENOENT
PATH=C:\Windows\System32;... -> spawn taskkill => exit 0
```

## Fix

- Copied the old repo `.codegraph/` metadata into the current repo for local code navigation.
- Updated `server/start.ps1` to repair Windows PATH before starting services.
- Updated `server/start.ps1` to launch child PowerShell/cmd through resolved system paths.
- Updated `server/start.ps1` to call:

```text
openclaw gateway run --port 19001 --auth token --token openclaw-local-token --bind loopback --force
```

- Set `OPENCLAW_SKIP_STARTUP_MODEL_PREWARM=1` for the Gateway startup path to avoid the nonessential startup warmup timeout.
- Updated `server/src/patchrelay/runtime.py` so programmatic OpenClaw Gateway startup also receives a repaired Windows PATH and the same default prewarm skip.

## Evidence

Focused runtime tests:

```text
uv run pytest tests/test_runtime.py
11 passed, 1 warning
```

Full test suite:

```text
uv run pytest
119 passed, 1 failed, 1 warning
```

The remaining failure is unrelated and pre-existing:

```text
tests/test_workers.py::test_claude_worker_uses_configured_command
expected old Claude args with --permission-mode acceptEdits
actual args use --dangerously-skip-permissions
```

Manual verification:

```text
gateway_ready=true port=19002 path_repaired=true
stripped=ENOENT
repaired_exit=0
```

## Regression Tests

Added coverage in `server/tests/test_runtime.py` for:

- OpenClaw runtime startup uses explicit `gateway run` arguments.
- OpenClaw runtime startup repairs Windows PATH and sets `OPENCLAW_SKIP_STARTUP_MODEL_PREWARM`.
- `with_windows_system_path` deduplicates PATH/PATH-like keys and prepends Windows system directories.
- `server/start.ps1` keeps `$PSScriptRoot`, repairs PATH, uses `$PowerShellExe`, and launches the explicit Gateway command.

## Status

DONE_WITH_CONCERNS

The reported Gateway startup crash is fixed and verified. The full suite still has one unrelated Claude worker expectation failure.
