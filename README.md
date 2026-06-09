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

The first implementation milestone focuses on a runnable Python Core API with a fake worker. Real Codex and Claude Code adapters, Git worktree isolation, and full test-profile execution are planned follow-up milestones.

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
- The project does not push to the remote repository unless explicitly requested.
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

Demo cleanup is manual for now. Remove `.patchrelay/` and delete any local `patchrelay/*` branches after inspection.
