# PatchRelay Quick Start — by Agent combination

Language: English | [简体中文](USAGE.zh-CN.md)

PatchRelay is a **bridge between two coding agents**. You pick a pair:

- **Agent1** — the front agent you talk to directly.
- **Agent2** — the delegate that runs the actual coding work in an isolated Git
  worktree, then returns status, diff, logs, and test results.

The launcher decides *how* the two connect from the pair you choose:

| Agent1 → Agent2 | Topology | What it feels like |
|---|---|---|
| `openclaw` → `claude` / `codex` | **Forward** | You chat in the OpenClaw dashboard; PatchRelay forwards each coding task to Agent2. |
| `claude` / `codex` → the other | **Ping-pong** | A desktop Claude/Codex session is your front agent; it relays tasks to Agent2 and reviews the result, hop after hop. |

## One command

```powershell
cd C:\path\to\PatchRelay\server
.\launch.ps1
```

`launch.ps1` asks two questions — *who is Agent1?* and *who is Agent2?* — then
starts exactly the components that pair needs. To skip the menu:

```powershell
.\launch.ps1 -Agent1 openclaw -Agent2 codex     # forward
.\launch.ps1 -Agent1 claude   -Agent2 codex     # ping-pong
.\launch.ps1 -Agent1 codex    -Agent2 claude -DryRun   # print the plan, launch nothing
```

Prerequisite (once): a working `patchrelay.yaml`. If you don't have one:

```powershell
uv run patchrelay setup --config .\patchrelay.yaml --yes
```

---

## Scenario A — OpenClaw → Claude (forward)

You talk to OpenClaw in the browser dashboard; Claude Code runs the changes.

```powershell
.\launch.ps1 -Agent1 openclaw -Agent2 claude
```

This starts the full stack (OpenClaw Gateway + PatchRelay Server + TUI +
Dashboard) and points OpenClaw's default worker at Claude.

1. Wait for the four windows/browser to come up (~30s).
2. In the dashboard, ask for a coding change:
   `"Add a list_by_status method to the TaskStore class and make the tests pass."`
3. OpenClaw calls `patchrelay_submit_task` automatically; Claude runs it in an
   isolated worktree.
4. Watch progress in the **TUI** window; read the diff / test result there or in
   the dashboard reply.

## Scenario B — OpenClaw → Codex (forward)

Same as A, but Codex is the delegate.

```powershell
.\launch.ps1 -Agent1 openclaw -Agent2 codex
```

Everything else is identical to Scenario A.

## Scenario C — Claude → Codex (ping-pong)

A **desktop Claude** session is your front agent. You talk to it; it delegates
implementation to Codex and reviews the result.

```powershell
.\launch.ps1 -Agent1 claude -Agent2 codex
```

This starts the PatchRelay Server + TUI, then opens a Claude session wired up as
Agent1 (`PATCHRELAY_URL` / `PATCHRELAY_TOKEN` / `PATCHRELAY_PARTNER=codex` set,
the Agent1 contract injected via `--append-system-prompt-file`).

1. In the Claude window, describe the work:
   `"Design a small calculator module in calc.py — add/subtract/multiply/divide with docstrings, then have it implemented and tested."`
2. Claude turns it into a brief and delegates:
   `patchrelay submit "<brief>" --worker codex --wait`.
3. Codex runs the change on an isolated branch; Claude reads the diff/tests,
   reviews, and either reports back or refines and delegates the next hop.
4. Monitor every hop in the **TUI**.

## Scenario D — Codex → Claude (ping-pong)

Mirror of C: a **desktop Codex** session is the front agent, delegating to Claude.

```powershell
.\launch.ps1 -Agent1 codex -Agent2 claude
```

Codex is opened with an initial prompt telling it to read its Agent1 contract
(`server/agent1/codex-agent1.md`) and relay coding work to Claude via the
`patchrelay` CLI.

---

## Stopping

```powershell
.\stop.ps1
```

Or close the windows. In ping-pong mode, closing the desktop Agent1 window ends
your front session; `.\stop.ps1` stops the Server (and Gateway, if running).

## Worker outcomes you may see

- **completed** — worker finished and the test profile passed.
- **failed** — worker exited non-zero, or tests failed. The diff is still captured.
- **timed_out** — the worker hit its wall-clock ceiling
  (`limits.worker_timeout_seconds`, default 30 min). If it left changes, the diff
  is preserved and tests still run — it is not discarded as a plain failure.

## Troubleshooting

**Port already in use** — `.\stop.ps1`, wait a few seconds, launch again.

**Agent1 window can't reach PatchRelay** — confirm the Server window is up on
port 8787 and that `patchrelay.yaml` has a real `server.token`. The Agent1
session reads `PATCHRELAY_URL` / `PATCHRELAY_TOKEN` from its environment; the
launcher sets these for you.

**OpenClaw doesn't see the tools (forward mode)** — the launcher delegates to
`start.ps1`, which reconciles the plugin/skill/tools with the gateway config. If
tools still don't appear, run `uv run patchrelay openclaw apply --config .\patchrelay.yaml --apply`.

**Change the target repo or tests** — edit `patchrelay.yaml`:

```yaml
repo:
  path: C:\path\to\your\project
  base_branch: main
tests:
  default:
    command: ["python", "-m", "pytest"]   # or ["npm", "test"], ["mvn", "test"]
```

## Handy commands

```powershell
uv run patchrelay runtime status --config .\patchrelay.yaml   # service status
uv run patchrelay tasks --token <token>                        # list tasks
uv run patchrelay logs <task-id> --token <token>               # task timeline
uv run patchrelay cleanup --config .\patchrelay.yaml --force   # clean worktrees/branches
```
