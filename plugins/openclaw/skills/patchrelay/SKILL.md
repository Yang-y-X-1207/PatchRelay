---
name: patchrelay
description: "Delegate coding tasks (features, refactors, bug fixes, test writing) to a local PatchRelay worker via patchrelay_submit_task; not for read-only lookup or trivial one-line edits."
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

Use PatchRelay to hand off any non-trivial coding work to an isolated local
worker (Claude Code / Codex). PatchRelay runs the task in a dedicated Git
worktree, runs the configured tests, and returns status + diff + logs +
artifacts.

## When to use

Use it for: implementing a feature, multi-file refactor, bug fix, writing or
fixing tests, "make change X across the repo".

Do NOT use it for: read-only questions about the code, explaining code, or a
single trivial edit you can answer inline.

## Tools

- `patchrelay_submit_task` — submit the work. Returns a `taskId`.
- `patchrelay_get_task` — poll status / read diff, logs, test output, artifacts.
- `patchrelay_cancel_task` — cancel a queued or running task.

## Standard loop

1. Call `patchrelay_submit_task` with a clear, self-contained `instruction`.
   - `worker`: leave `auto` unless the user names one (`claude` / `codex`).
   - `testProfile`: `default` unless the user specifies another.
2. Take the returned `taskId`.
3. Poll with `patchrelay_get_task` until `status` is terminal
   (`completed` / `failed` / `canceled`).
4. Report back to the user: summary, changed files, test result, and where the
   diff/artifacts are. On failure, surface the worker log tail; offer to
   resubmit with a refined instruction.

## Rules

- Write the `instruction` so the worker needs no follow-up: goal, target files
  or area, acceptance/test expectation.
- One task at a time (MVP runs serially); don't fan out.
- Never hand-edit the repo yourself as a silent substitute when PatchRelay is
  the intended path — if it fails, report and ask.
