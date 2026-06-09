# PatchRelay

Language: English | [简体中文](README.zh-CN.md)

PatchRelay is a local remote-execution relay for agentic coding tasks.

It is designed to run on a developer machine or trusted internal machine, receive coding tasks from OpenClaw or another A2A-compatible client, dispatch those tasks to local coding workers such as Codex or Claude Code, and return task status, logs, diffs, and test results.

## Current MVP Direction

PatchRelay intentionally does not rebuild an IM gateway or a full coding agent. The planned MVP is:

```text
OpenClaw Gateway
  -> PatchRelay OpenClaw Tool Plugin
  -> PatchRelay Local A2A-compatible Server
  -> Serial Task Queue
  -> Fake Worker first, then Codex / Claude Code adapters
```

The current implementation includes a runnable Python Core API, SQLite task persistence, serial task queue, Git worktree isolation, configurable test profiles, a fake worker demo path, and command-line adapters for Codex and Claude Code. Follow-up work will continue improving real worker operation, approval, and delivery workflows.

## Repository Layout

```text
.
├── MEMORY.md              # Product memory and direction notes
├── prd.md                 # Product requirements document
├── server/                # Python PatchRelay Core
└── plugins/openclaw/      # OpenClaw Tool Plugin spike
```

## Development Rules

- Windows is the first supported development environment.
- Major work starts from `main` on a feature branch.
- Feature branches are committed locally and merged back to `main`.
- Push behavior follows the current collaboration agreement; during this phase completed feature branches are merged to `main` and pushed after verification.
- The recommended Python dependency manager is `uv`; the code also supports standard `python -m pip` workflows.

## Documentation

- Product requirements: [prd.md](prd.md)
- Project memory: [MEMORY.md](MEMORY.md)

## Local Demo

The current demo uses the fake worker. It creates a task branch/worktree, writes `fake-change.txt`, runs a lightweight test profile, and returns artifacts through the API/CLI.

From the repository root:

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
uv sync --extra dev
Copy-Item .\examples\demo.patchrelay.yaml .\patchrelay.yaml
```

Terminal 1:

```powershell
uv run patchrelay serve --config .\patchrelay.yaml
```

Terminal 2:

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
$env:PATCHRELAY_TOKEN="demo-token"
uv run patchrelay doctor --config .\patchrelay.yaml
uv run patchrelay submit "Create a demo fake worker change" --worker fake --wait --token demo-token
uv run patchrelay tasks --token demo-token
```

Expected result:

- task status is `completed`
- branch starts with `patchrelay/`
- changed files include `fake-change.txt`
- test status is `passed`

After inspection, preview cleanup targets:

```powershell
uv run patchrelay cleanup --config .\patchrelay.yaml
```

Remove PatchRelay demo worktrees, local `patchrelay/*` branches, and `.patchrelay/` state:

```powershell
uv run patchrelay cleanup --config .\patchrelay.yaml --force
```
