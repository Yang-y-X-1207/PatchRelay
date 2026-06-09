# PatchRelay

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
