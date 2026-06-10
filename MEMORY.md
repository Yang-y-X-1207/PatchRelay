# PatchRelay Project Memory

## Product Name

PatchRelay

## Positioning

PatchRelay is a remote execution relay for agentic coding tasks.

Chinese positioning: 面向 Agent 编码任务的远程执行中继。

## Core Direction

PatchRelay should not rebuild a full IM gateway or a full coding agent from scratch.

The product should connect remote gateways or message entrypoints to local professional coding workers such as Claude Code and Codex. The core value is reliable task handoff, execution isolation, progress reporting, diff/test result collection, and controlled Git delivery.

## Current Stage

PatchRelay is currently in a basic-usable MVP stage.

The immediate goal is to complete and stabilize the real end-to-end execution loop: OpenClaw or another gateway sends a coding task, PatchRelay accepts and normalizes it, a real coding worker such as Claude Code or Codex executes it, and PatchRelay returns status, logs, diffs, test results, and final outcome to the caller.

At this stage, the priority is correctness of the core flow, clear protocol boundaries, practical debugging visibility, and a small reliable single-node deployment. Do not overbuild distributed infrastructure before the real task loop is proven useful.

High availability, high reliability, and high concurrency are explicit later-stage system goals. The current MVP should keep an upgrade path for them, but should not delay the first usable integration by implementing the full production architecture too early.

## Architecture Sketch

```text
IM / Remote Gateway
        |
        v
PatchRelay Bridge
        |
        v
Coding Worker
   - Codex adapter
   - Claude Code adapter
   - workspace sandbox
   - git branch / commit / optional push
        |
        v
Status / logs / diff / PR result returned to the gateway
```

Short form:

```text
Gateway -> PatchRelay Bridge -> Coding Worker -> Git/PR/status callback
```

## Decision From EasyCoding

EasyCoding attempted to build the whole stack: IM gateway, multi-channel adapters, sessions, task queues, workspace isolation, agent loop, tool system, local code editing, and Git workflow.

That scope is too broad for the current stage. PatchRelay should reduce scope and avoid rebuilding infrastructure that can be delegated to existing gateways and coding agents.

The new focus is the bridge layer:

- accept remote coding tasks from a gateway or API
- normalize them into a coding-task protocol
- dispatch them to a local coding worker
- collect logs, file changes, test results, and diffs
- require human approval before risky Git actions such as push
- report final status back to the caller

## MVP Defaults

- Support one local repository first.
- Support one task at a time with a serial queue.
- Support two worker adapters: Codex and Claude Code.
- Use branch-per-task execution.
- Return progress logs, changed files, diff summary, test result, and final status.
- Require manual confirmation before `git push`.
- Keep the protocol simple before implementing full A2A compatibility.

## Naming Principle

The product name must not be biased toward OpenClaw, Claude Code, Codex, or any single upstream/downstream tool.

PatchRelay should remain tool-neutral:

- any gateway can send a task
- any coding worker can execute it
- any Git hosting provider can receive the result later

## Future Direction

After the MVP is stable, PatchRelay can evolve toward an A2A-compatible coding execution system with:

- agent capability discovery
- task lifecycle APIs
- streaming status updates
- structured artifacts
- resumable task state
- richer approval policies
- multiple repository/workspace support
