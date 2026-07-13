---
name: patchrelay
description: "MUST use for any coding task: implementing features, refactors, bug fixes, test writing, multi-file changes. Call patchrelay_submit_task immediately — do not hand-code, do not use HTTP, do not claim the tool is unavailable."
metadata:
  {
    "openclaw":
      {
        "emoji": "🛰️",
        "requires":
          {
            "config": ["skills.entries.patchrelay.enabled", "plugins.entries.patchrelay.enabled"]
          }
      }
  }
---

# PatchRelay

PatchRelay relays coding tasks to an isolated local worker (Claude Code / Codex).
It runs the task in a dedicated Git worktree, executes the configured test suite,
and returns status, diff, logs, and artifacts.

## Hard rules — no exceptions

- **The tools exist. Call them.** `patchrelay_submit_task`, `patchrelay_get_task`,
  and `patchrelay_cancel_task` are registered and available. Never say "I don't
  have this tool" — just call it.
- **Use the tool functions. Never use HTTP.** Do not use `curl`,
  `Invoke-RestMethod`, or any HTTP client to call the PatchRelay API manually.
  The only correct method is a tool function call.
- **No silent fallback.** If you are unsure whether PatchRelay is running, call
  the tool anyway and report any error to the user. Do not silently start
  writing code yourself instead.
- **Act immediately.** When a coding task arrives, your first action is to call
  `patchrelay_submit_task`. Do not explain, confirm, or ask first — unless the
  task clearly falls under "Do NOT use" below.

## When to use

Use PatchRelay for any of the following:

- Implementing a new feature, interface, or module
- Multi-file refactor, rename, or code relocation
- Bug fix that requires changing code
- Writing or fixing tests
- "Change X to Y", "add B to A", "delete C"
- Any change that produces a diff

**Do NOT use for:**

- Read-only questions (explain code, analyse architecture, answer concepts)
- A single trivial inline edit you can answer in one line

When in doubt, default to PatchRelay.

## Tools

- `patchrelay_submit_task` — submit the task; returns a `taskId`
- `patchrelay_get_task` — poll status; read diff, logs, test output, artifacts
- `patchrelay_cancel_task` — cancel a queued or running task

## Standard loop

1. Call `patchrelay_submit_task` with a complete `instruction`:
   - Goal (what to do), scope (which files / modules), acceptance criteria (what tests must pass)
   - `worker`: `auto` by default; use `claude` or `codex` if the user specifies
   - `testProfile`: `default` unless the user specifies another
2. Capture the returned `taskId`.
3. Poll `patchrelay_get_task` until `status` is terminal
   (`completed` / `failed` / `cancelled`).
4. Report to the user: change summary, modified files, test result, diff/artifact locations.
   - On failure: show the worker log tail and offer to resubmit with a refined instruction.

## Writing a good instruction

The worker cannot ask follow-up questions. Include everything it needs:

- **What** to do
- **Where** (target files or module)
- **How to verify** (expected test output or acceptance condition)

Example: `"Add a list_by_status(status) method to the TaskStore class in
server/src/patchrelay/tasks.py that returns all tasks with the given status.
All pytest tests must pass."`

## Constraints

- Submit one task at a time — the MVP queue is serial; do not fan out.
- After submitting, wait for the worker result. Do not edit the repo yourself.
