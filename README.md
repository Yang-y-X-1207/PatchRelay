# PatchRelay

Language: English | [Simplified Chinese](README.zh-CN.md)

PatchRelay is a local execution relay for agentic coding tasks. It receives coding requests from OpenClaw or another gateway, sends the work to a local coding worker such as Claude Code or Codex, and returns task status, logs, diffs, test results, and artifacts.

For hands-on startup and testing, start with the quick start guide: [USAGE.md](USAGE.md).

## Current Stage

PatchRelay is currently a **basic usable MVP**. The single-node execution loop is implemented and has been verified locally:

```text
OpenClaw Dashboard/Gateway
  -> PatchRelay OpenClaw plugin
  -> PatchRelay Python server
  -> Claude Code or Codex worker
  -> Git worktree, tests, artifacts
  -> OpenClaw result view or PatchRelay TUI
```

The project is not yet a production high-availability system. The current focus is a stable local loop: submit a coding task, isolate it in a Git worktree, run a configured worker, collect artifacts, and inspect the result.

## Implemented

- Python FastAPI PatchRelay server with bearer-token protected task APIs.
- A2A-like endpoints: health, agent card, message send/stream, task list/get/events/cancel.
- SQLite-backed local task persistence.
- Serial task queue: one task runs at a time in the current MVP.
- Git branch and worktree isolation per task.
- Worker adapters for `fake`, `claude`, and `codex`.
- Configurable test profiles that run after worker execution.
- Artifact collection for summary, changed files, diff, worker logs, and test output.
- OpenClaw TypeScript plugin exposing `patchrelay_submit_task`, `patchrelay_get_task`, and `patchrelay_cancel_task`.
- OpenClaw setup helpers for plugin install/config patching.
- CLI commands for init, setup, doctor, runtime start/status/stop, smoke tests, submit, wait, logs, tasks, cancel, and cleanup.
- Full-screen Textual TUI with task dashboard, filtering, task detail, artifact preview, task submission, setup wizard, runtime controls, smoke test action, auto-refresh, and keyboard shortcuts.
- Windows PowerShell `server/start.ps1` and `server/stop.ps1` scripts for local one-command startup/shutdown.

## Not Implemented Yet

- Distributed task queue or multi-worker pool.
- High-availability control plane.
- Multi-repository registry and per-repo permission model.
- Automatic commit, push, or pull request creation by default.
- Cloud relay or reverse tunnel mode.
- Production-grade auth, audit, rate limiting, and tenancy.
- Java control-plane microservice. This remains a later-stage architecture plan after the Python local loop is stable.

## Quick Start

The user-facing quick start lives in [USAGE.md](USAGE.md). It covers:

- installing dependencies
- running `server/start.ps1`
- starting OpenClaw Gateway, PatchRelay Server, PatchRelay TUI, and OpenClaw Dashboard
- submitting a task from OpenClaw
- watching task progress in the TUI
- stopping services with `server/stop.ps1`
- common local troubleshooting

Short version:

```powershell
cd C:\path\to\PatchRelay\server
.\start.ps1
```

Then wait for the Gateway, server, TUI, and browser dashboard to finish starting. See [USAGE.md](USAGE.md) for the complete walkthrough.

## Repository Layout

```text
.
|-- README.md               # Project overview and current status
|-- README.zh-CN.md         # Chinese README
|-- USAGE.md                # Quick start and local testing guide
|-- prd.md                  # Product requirements and roadmap notes
|-- ARCHITECTURE_ROADMAP.md # Architecture evolution notes
|-- server/                 # Python PatchRelay server, CLI, TUI, scripts
|-- plugins/openclaw/       # OpenClaw TypeScript plugin
|-- docs/                   # Additional planning and product documents
```

## Requirements

Recommended local environment:

- Windows 10/11
- Git
- Python 3.10+
- `uv`
- Node.js 22+
- npm
- OpenClaw 2026.6.1 or newer
- Claude Code CLI for the Claude worker
- Codex CLI for the Codex worker

Check tools:

```powershell
git --version
python --version
uv --version
node --version
npm --version
openclaw --version
claude --version
codex --version
```

## Install

From the repository root:

```powershell
cd .\server
uv sync --extra dev --extra tui

cd ..\plugins\openclaw
npm install
npm run build
```

Generate or repair local configuration:

```powershell
cd ..\..\server
uv run patchrelay setup --config .\patchrelay.yaml
```

For non-interactive local defaults:

```powershell
uv run patchrelay setup --config .\patchrelay.yaml --yes
```

## Common Commands

Run diagnostics:

```powershell
uv run patchrelay doctor --config .\patchrelay.yaml
uv run patchrelay setup verify --config .\patchrelay.yaml
```

Start managed runtime services:

```powershell
uv run patchrelay runtime start --config .\patchrelay.yaml
uv run patchrelay runtime status --config .\patchrelay.yaml
uv run patchrelay runtime stop --config .\patchrelay.yaml
```

Run the TUI:

```powershell
uv run patchrelay ui --config .\patchrelay.yaml
```

Run a local smoke test:

```powershell
uv run patchrelay smoke --config .\patchrelay.yaml --worker fake
```

Submit a task directly to PatchRelay:

```powershell
uv run patchrelay submit "Add a short usage note to README.md" --worker fake --wait --token <patchrelay-token>
```

Run a smoke test through OpenClaw Gateway:

```powershell
uv run patchrelay smoke `
  --config .\patchrelay.yaml `
  --via openclaw `
  --worker fake `
  --gateway-url http://127.0.0.1:19001 `
  --gateway-token openclaw-local-token
```

## OpenClaw Integration

Build and validate the plugin:

```powershell
cd .\plugins\openclaw
npm run plugin:validate
```

Install the local plugin into OpenClaw:

```powershell
openclaw plugins install C:\path\to\PatchRelay\plugins\openclaw --link
```

Apply OpenClaw setup from the PatchRelay config:

```powershell
cd C:\path\to\PatchRelay\server
uv run patchrelay openclaw apply --config .\patchrelay.yaml --apply
openclaw plugins inspect patchrelay --runtime --json
```

OpenClaw should expose:

- `patchrelay_submit_task`
- `patchrelay_get_task`
- `patchrelay_cancel_task`

## API Surface

Main server endpoints:

- `GET /health`
- `GET /.well-known/agent-card.json`
- `POST /message:send`
- `POST /message:stream`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/events`
- `POST /tasks/{task_id}:cancel`

Task responses include status, worker, phase, branch, worktree path, events, and artifacts. Event timelines can be paged with `/tasks/{task_id}/events?after=<sequence>`.

## Development Verification

Run server tests:

```powershell
cd .\server
uv run pytest
```

Run plugin tests:

```powershell
cd .\plugins\openclaw
npm test
npm run plugin:validate
```

## MVP Limits

The MVP intentionally keeps the system small:

- one local repository first
- one task at a time
- branch/worktree isolation per task
- local SQLite task persistence
- manual cleanup via `patchrelay cleanup`
- no automatic Git push or PR creation by default
- no distributed worker pool yet

The long-term direction is to keep Python focused on the agent execution path, then introduce a Java control-plane service later for high concurrency, high availability, scheduling, auth, and production operations.
