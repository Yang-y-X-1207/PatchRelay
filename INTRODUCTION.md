# PatchRelay — a bridge between two coding agents

Language: English | [简体中文](INTRODUCTION.zh-CN.md)

## The one-sentence idea

**PatchRelay lets one AI coding agent hand real coding work to another, safely,
on your machine.** You pick two agents. One is the front you talk to; the other
does the implementation in an isolated Git worktree and hands back a reviewed,
tested diff.

## Why it exists

A single coding agent has to do everything in one context: plan, edit, run
tests, and keep track of it all. That gets crowded, and it couples "the agent I
like talking to" with "the agent that's best at grinding out the change."

PatchRelay splits those roles:

- **Agent1 (front)** — understands your intent, plans, reviews. Stays in a clean
  context because it isn't the one editing files.
- **Agent2 (delegate)** — receives a self-contained brief, makes the change in an
  isolated branch, runs the test suite, and returns a diff + logs + result.

The change never touches your working tree directly. Every task runs in its own
`git worktree` on its own branch, so a bad run is a branch you throw away, not a
mess in your repo.

## The mental model: a bridge

```
        you
         │  talk / read results
         ▼
   ┌───────────┐        task brief        ┌───────────┐
   │  Agent1   │ ───────────────────────▶ │ PatchRelay│
   │  (front)  │ ◀─────────────────────── │  (bridge) │
   └───────────┘   status · diff · tests  └─────┬─────┘
                                                │ runs in isolation
                                                ▼
                                          ┌───────────┐
                                          │  Agent2   │
                                          │ (delegate)│──▶ git worktree + tests
                                          └───────────┘
```

PatchRelay is the bridge in the middle. It doesn't write code and it isn't an
agent — it queues the task, isolates it, runs the chosen worker, runs your
tests, and collects the artifacts.

## Two topologies, four combinations

Which agent you put in front decides how the bridge behaves.

### Forward — Agent1 = OpenClaw

You chat in the OpenClaw dashboard. When you ask for a coding change, OpenClaw
forwards it once to Agent2 and shows you the result. One hop, one direction.

```
  OpenClaw dashboard ──▶ PatchRelay ──▶ Claude or Codex ──▶ worktree + tests
       (you chat)                          (delegate)
```

- **OpenClaw → Claude**
- **OpenClaw → Codex**

### Ping-pong — Agent1 = Claude or Codex

A desktop Claude/Codex session is your front agent. You talk to *it*. It turns
your request into a brief, delegates to Agent2, reads the returned diff and test
result, reviews it, and — for multi-step work — sends the next brief. Back and
forth, hop after hop, with Agent1 as planner/reviewer and Agent2 as implementer.

```
  you ─▶ desktop Claude ─▶ PatchRelay ─▶ Codex ─▶ worktree + tests
   ▲        (Agent1)                     (Agent2)        │
   └──────── review ◀── diff · tests ◀───────────────────┘
                    (repeat for the next step)
```

- **Claude → Codex**
- **Codex → Claude**

## What you get back from every task

- **status** — `completed`, `failed`, or `timed_out`
- **diff** — the exact change, always captured (even on failure/timeout)
- **test result** — output of your configured test profile
- **logs & artifacts** — the worker's output and a task summary
- **branch / worktree** — where the change lives, isolated from your main tree

## What it is not (yet)

PatchRelay is a **local, single-node MVP**. It runs one task at a time, on one
repository, with no automatic commit/push or PR creation. There is no cloud
relay or distributed worker pool. The focus is a solid local loop: submit →
isolate → run → test → inspect. See [ARCHITECTURE_ROADMAP.md](ARCHITECTURE_ROADMAP.md)
for where it's headed.

## Start here

- **Get running in one command:** [USAGE.md](USAGE.md) — quick start by Agent combination.
- **Full reference:** [README.md](README.md) — install, config, API surface, commands.
