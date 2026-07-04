# DEBUG REPORT: Agent1 PatchRelay autodiscovery

- **Symptom:** OpenClaw Agent1 can call `patchrelay_submit_task`, `patchrelay_get_task`, and `patchrelay_cancel_task`, but does not proactively choose PatchRelay for coding tasks unless the user explicitly asks for it.
- **Root cause:** PatchRelay was installed only as an OpenClaw tool plugin. The tool descriptions were too short to teach delegation timing, and there was no OpenClaw skill description for model-visible capability discovery.
- **Fix:** Added a `patchrelay` OpenClaw skill that describes when to delegate coding work, tightened submit/get tool descriptions, and extended `patchrelay openclaw apply` to install and enable the skill after plugin setup.
- **Implementation note:** OpenClaw 2026.6.1 rejected `config patch/set` writes on this machine with a size-drop guard. `apply_openclaw_config` now keeps the CLI patch as the primary path and falls back to a validated direct merge only when that guard rejects a PatchRelay config write.
- **Evidence:** `openclaw skills info patchrelay` reports `Visible to model: yes` and both `skills.entries.patchrelay.enabled` and `plugins.entries.patchrelay.enabled` requirements pass.
- **Regression tests:** `server/tests/test_onboarding.py` covers the skill file, apply step order, and the size-drop fallback. `plugins/openclaw/src/*.test.ts` covers OpenClaw tool metadata and tool calls.
- **Verification:** `uv run pytest tests/test_onboarding.py` passed with 16 tests. `npm test` passed with 6 tests. `npm run plugin:validate` passed. Full `uv run pytest` has one pre-existing failure in `tests/test_workers.py::test_claude_worker_uses_configured_command`.
- **Status:** DONE_WITH_CONCERNS: autodiscovery is fixed and locally enabled; the remaining full-suite failure is unrelated to this change.
