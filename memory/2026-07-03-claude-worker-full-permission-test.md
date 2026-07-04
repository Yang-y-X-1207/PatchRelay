# DEBUG REPORT: Claude worker full-permission test

- **Symptom:** Full server test suite failed at `tests/test_workers.py::test_claude_worker_uses_configured_command`.
- **Root cause:** `server/src/patchrelay/workers.py` intentionally launches Claude with `--dangerously-skip-permissions`, but the test still expected the older `--permission-mode acceptEdits --allowedTools Write,Edit,Read` argument set.
- **Fix:** Updated the Claude worker test expectation to assert the full-permission argument.
- **Evidence:** `uv run pytest tests/test_workers.py::test_claude_worker_uses_configured_command -q` passed; `uv run pytest tests/test_workers.py` passed; full `uv run pytest` passed with 124 tests.
- **Regression test:** `server/tests/test_workers.py::test_claude_worker_uses_configured_command`.
- **Status:** DONE
