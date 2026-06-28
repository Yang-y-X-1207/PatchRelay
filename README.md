# PatchRelay

Language: English | [Simplified Chinese](README.zh-CN.md)

PatchRelay is a local execution relay for agentic coding tasks. It receives coding requests from OpenClaw or another gateway, dispatches them to a local coding worker such as Claude Code or Codex, and returns task status, logs, diffs, test results, and final artifacts.

**Current Status**: ✅ **Production-Ready MVP** — The complete end-to-end chain is operational and has been validated with production-level tasks.

**🚀 [Quick Start Guide →](USAGE.md)** | One-click startup: `cd PatchRelay-tui\server && .\start.ps1`

---

## Verified Integration Chain

```text
User (OpenClaw Dashboard)
  ↓
OpenClaw Gateway (port 19001)
  ↓
PatchRelay OpenClaw Plugin (patchrelay_submit_task tool)
  ↓
PatchRelay Server (port 8787, HTTP API)
  ↓
Task Queue (serial, isolated Git worktrees)
  ↓
Claude Code / Codex Worker (non-interactive, full permissions)
  ↓
Artifacts (diff, logs, changed files, test results)
  ↓
OpenClaw Dashboard (result display)
  ↓
PatchRelay TUI Monitor (real-time task tracking)
```

**Design Principles:**
- OpenClaw handles user interaction, chat gateway, and result display
- PatchRelay manages task execution, Git isolation, and worker orchestration
- Claude Code (or Codex) performs the actual code modifications
- Each task runs in an isolated Git worktree on branch `patchrelay/task-<id>`

---

## What PatchRelay Does

- ✅ Accepts coding tasks from OpenClaw Gateway or direct HTTP API calls
- ✅ Creates isolated Git worktrees (one per task, automatic cleanup)
- ✅ Dispatches tasks to configurable workers: `fake` (testing), `claude` (Claude Code), `codex` (Codex CLI)
- ✅ Runs configurable test profiles after worker execution
- ✅ Collects artifacts: unified diff, changed files, stdout/stderr, test results
- ✅ Exposes HTTP API for task submission, status queries, cancellation
- ✅ Provides real-time TUI dashboard with live logs and diff viewer
- ✅ Supports one-click startup of all services (Gateway, Server, TUI, Dashboard)

---

## What PatchRelay Does NOT Do

- ❌ Does not rebuild an IM gateway or chat platform
- ❌ Does not implement a full coding agent from scratch
- ❌ Does not require OpenClaw to execute shell commands directly
- ❌ Does not automatically push Git changes (manual review required)
- ❌ Does not (yet) provide production-grade clustering, distributed queues, or worker pools

For cloud SaaS evolution plans, see [ARCHITECTURE_ROADMAP.md](ARCHITECTURE_ROADMAP.md).

---

## Current Features

**Completed in MVP:**

| Component | Status | Description |
|-----------|--------|-------------|
| **One-click startup** | ✅ | `start.ps1` launches Gateway, Server, TUI, Dashboard |
| **OpenClaw plugin** | ✅ | Tools: `patchrelay_submit_task`, `patchrelay_get_task`, `patchrelay_cancel_task` |
| **Claude Code worker** | ✅ | Full permissions (`--dangerously-skip-permissions`), non-interactive |
| **Codex worker** | ✅ | JSON output mode with structured results |
| **Git worktree isolation** | ✅ | Branch `patchrelay/task-<id>`, automatic creation and cleanup |
| **TUI monitor** | ✅ | Dashboard, task list, live logs, diff viewer, artifacts |
| **HTTP API** | ✅ | `/tasks` (submit, list, get, cancel), `/health`, `/a2a/agent-card` |
| **CLI toolkit** | ✅ | `init`, `doctor`, `smoke`, `submit`, `tasks`, `get`, `cancel`, `cleanup`, `runtime`, `openclaw apply` |
| **Test runner** | ✅ | Configurable profiles with timeout and pass/fail detection |
| **Production validation** | ✅ | Successfully executed production-level coding tasks |

**Known Limitations (MVP scope):**
- Serial task queue (one task at a time)
- Single repository support
- No distributed worker pool
- No high-availability or failover
- Manual cleanup for old worktrees (or use `patchrelay cleanup`)

---

## Repository Layout

```text
PatchRelay/                          # Documentation root
|-- README.md                        # This file (English)
|-- README.zh-CN.md                  # 中文版
|-- USAGE.md                         # Quick start and daily usage guide
|-- ARCHITECTURE_ROADMAP.md          # Architecture evolution roadmap (Phase 1: local, Phase 2: cloud SaaS)
|-- prd.md                           # Product requirements document
|
|-- PatchRelay-tui/                  # Main project directory
    |-- server/                      # Python PatchRelay Core API and CLI
    |   |-- src/patchrelay/          # Source code
    |   |   |-- cli.py               # CLI entry point (Typer-based)
    |   |   |-- app.py               # FastAPI server
    |   |   |-- tasks.py             # Task lifecycle management
    |   |   |-- workers.py           # Worker adapters (fake, claude, codex)
    |   |   |-- git_workspace.py    # Git worktree management
    |   |   |-- test_runner.py      # Test profile execution
    |   |   |-- task_store.py       # SQLite task persistence
    |   |   |-- tui/                 # TUI application (Textual-based)
    |   |       |-- app.py           # Dashboard entry point
    |   |       |-- screens/         # Dashboard, task detail, submit, setup wizard
    |   |       |-- widgets/         # Task table, live log, diff viewer, status badges
    |   |-- tests/                   # Pytest test suite (80+ tests)
    |   |-- start.ps1                # One-click startup (Gateway + Server + TUI + Dashboard)
    |   |-- stop.ps1                 # Stop all services
    |   |-- patchrelay.yaml          # Server configuration (generated by `patchrelay init`)
    |
    |-- plugins/openclaw/            # OpenClaw tool plugin (TypeScript)
        |-- src/                     # Source code
        |   |-- index.ts             # Plugin entry point
        |   |-- tools.ts             # Tool definitions (submit_task, get_task, cancel_task)
        |   |-- client.ts            # HTTP client
        |-- dist/                    # Built plugin (JavaScript)
        |-- package.json             # npm package definition
```

---

## Requirements

**Platform:**
- Windows 10/11 (primary platform, tested)
- macOS / Linux (untested but should work)

**Dependencies:**
- Git
- Python 3.10+
- `uv` (Python package manager)
- Node.js 22+
- npm
- **OpenClaw 2026.6.1+** (for gateway integration)
- **Claude Code CLI** (required for `claude` worker)
- **Codex CLI** (required for `codex` worker)

**Verify installed tools:**

```powershell
git --version
python --version
uv --version
node --version
npm --version
openclaw --version
claude --version   # Claude Code CLI
codex --version    # Codex CLI
```

---

## Quick Setup

### 1. Clone and Install Dependencies

```powershell
# Navigate to project
cd path\to\PatchRelay\PatchRelay-tui

# Install Python server dependencies
cd server
uv sync --extra dev

# Install and build OpenClaw plugin
cd ..\plugins\openclaw
npm install
npm run build
npm run plugin:validate
```

### 2. Initialize Configuration

```powershell
cd ..\..\server
uv run patchrelay init
```

This creates `patchrelay.yaml` with:
- Repository path (default: parent directory)
- Base branch (default: `main`)
- Server token (auto-generated)
- Worker commands (auto-detected: `claude`, `codex`)
- Test profile (default: prints "tests ok")

### 3. Install OpenClaw Plugin

```powershell
cd ..\plugins\openclaw
openclaw plugins link .

# Verify
openclaw plugins list | Select-String "patchrelay"
```

Apply plugin config to OpenClaw:

```powershell
cd ..\..\server
uv run patchrelay openclaw apply --config .\patchrelay.yaml --apply
```

Or manually edit `~/.config/openclaw/config.json`:

```json
{
  "plugins": {
    "entries": {
      "patchrelay": {
        "enabled": true,
        "config": {
          "baseUrl": "http://127.0.0.1:8787",
          "token": "your-token-from-patchrelay-yaml"
        }
      }
    }
  }
}
```

### 4. Run Diagnostics

```powershell
# Check configuration and dependencies
uv run patchrelay doctor --config .\patchrelay.yaml

# Smoke test with fake worker
uv run patchrelay smoke --config .\patchrelay.yaml --worker fake
```

### 5. Start All Services

```powershell
.\start.ps1
```

Wait ~30 seconds for all services to start. You'll see 3 PowerShell windows + browser:
- OpenClaw Gateway (port 19001)
- PatchRelay Server (port 8787)
- PatchRelay TUI Monitor
- OpenClaw Dashboard (browser)

**See [USAGE.md](USAGE.md) for detailed usage guide.**

---

## CLI Reference

The `patchrelay` CLI provides these commands:

| Command | Purpose |
|---------|---------|
| `serve` | Run the PatchRelay HTTP server (uvicorn, port 8787) |
| `ui` | Launch the TUI dashboard |
| `init` | Generate `patchrelay.yaml` configuration |
| `doctor` | Check configuration and dependencies |
| `smoke` | Submit a test task and verify the full chain |
| `submit <instruction>` | Submit a coding task via CLI |
| `tasks` | List all tasks |
| `get <task_id>` | Get task details and artifacts |
| `cancel <task_id>` | Cancel a running task |
| `wait <task_id>` | Wait for task completion |
| `logs <task_id>` | Print raw worker logs |
| `cleanup` | Remove old worktrees and branches |
| `runtime start` | Start PatchRelay and OpenClaw Gateway as background services |
| `runtime stop` | Stop background services |
| `runtime status` | Check runtime service status |
| `openclaw apply` | Apply PatchRelay config to OpenClaw plugin settings |

**Examples:**

```powershell
# Submit a task and wait for completion
uv run patchrelay submit "Add a usage example to README.md" --worker claude --wait

# List tasks
uv run patchrelay tasks --token <your-token>

# Get task details
uv run patchrelay get task-abc123 --token <your-token>

# Clean up old worktrees
uv run patchrelay cleanup --config .\patchrelay.yaml --force
```

---

## HTTP API

Base URL: `http://127.0.0.1:8787`

Authentication: `Authorization: Bearer <token>` (from `patchrelay.yaml`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check (version, uptime) |
| `/a2a/agent-card` | GET | A2A agent capability card (public, no auth) |
| `/tasks` | POST | Submit a new task |
| `/tasks` | GET | List all tasks |
| `/tasks/{task_id}` | GET | Get task details and artifacts |
| `/tasks/{task_id}:cancel` | POST | Cancel a running task |

**Submit task example:**

```bash
curl -X POST http://127.0.0.1:8787/tasks \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Add error handling to login function",
    "worker": "claude",
    "test_profile": "default"
  }'
```

---

## Configuration

`patchrelay.yaml` structure:

```yaml
server:
  host: 127.0.0.1
  port: 8787
  token: <auto-generated-secure-token>

repo:
  path: C:\path\to\your\repo
  base_branch: main
  state_dir: .patchrelay

worker:
  default: auto                    # auto | fake | claude | codex
  fake_command: internal
  codex_command: codex
  claude_command: claude

tests:
  default:
    command: ["python", "-c", "print('tests ok')"]
    timeout_seconds: 300
    expect_zero_exit: true

limits:
  task_timeout_seconds: 7200       # 2 hours
  worktree_retention_days: 7
```

---

## Worker Details

### Fake Worker
- Built-in test worker
- Writes a dummy `FAKE_CHANGE.txt` file
- Always succeeds (for testing the chain)

### Claude Worker
- Launches Claude Code CLI with `--dangerously-skip-permissions` (full non-interactive mode)
- Flags: `-p`, `--output-format json`, `--disable-slash-commands`, `--no-session-persistence`
- Can execute Bash commands, read/write files, no permission prompts

### Codex Worker
- Launches Codex CLI with `exec --json`
- Structured JSON output with task results

---

## Git Workflow

1. **Task submitted** → Server creates branch `patchrelay/task-<id>`
2. **Worktree created** → `.patchrelay/worktrees/<id>/`
3. **Worker executes** → Changes files in the worktree
4. **Tests run** → Configured test profile executes
5. **Artifacts collected** → diff, changed files, logs, test results
6. **Task completes** → Worktree remains for review
7. **Manual review** → User inspects diff in TUI or via `patchrelay get`
8. **Manual merge** → User merges branch if satisfied (no automatic push)
9. **Cleanup** → `patchrelay cleanup` removes old worktrees

---

## Development

### Run Tests

```powershell
cd PatchRelay-tui\server
uv run pytest                    # Run all tests
uv run pytest -v                 # Verbose
uv run pytest tests/test_tasks.py  # Specific file
```

### Run Plugin Tests

```powershell
cd PatchRelay-tui\plugins\openclaw
npm test
npm run plugin:validate
```

---

## Troubleshooting

### Port already in use

```powershell
# Stop all services
.\stop.ps1

# Verify ports are free
netstat -ano | findstr ":8787"
netstat -ano | findstr ":19001"
```

### OpenClaw plugin not loaded

```powershell
# Verify plugin is linked
openclaw plugins list | Select-String "patchrelay"

# Re-link if needed
cd ..\plugins\openclaw
openclaw plugins link .

# Restart OpenClaw Gateway
.\stop.ps1
.\start.ps1
```

### Worker not found

```powershell
# Check worker commands
claude --version
codex --version

# Update patchrelay.yaml if paths differ
```

---

## Architecture Roadmap

**Phase 1 (Current): Local Deployment**
- Single-node execution
- Serial task queue
- SQLite persistence
- Git worktree isolation
- Target: 10-50 concurrent tasks

**Phase 2 (Planned): Cloud SaaS**
- Multi-tenant architecture
- Distributed worker pool
- Java Gateway for high concurrency
- Local agent for code security
- Target: 1000+ concurrent tasks

See [ARCHITECTURE_ROADMAP.md](ARCHITECTURE_ROADMAP.md) for details.

---

## Documentation

- **[USAGE.md](USAGE.md)** — Quick start and daily usage
- **[prd.md](prd.md)** — Product requirements
- **[ARCHITECTURE_ROADMAP.md](ARCHITECTURE_ROADMAP.md)** — Evolution roadmap

---

## License

(Add your license here)

---

**Enjoy using PatchRelay!** 🚀

For questions or issues, see the documentation or run `uv run patchrelay doctor`.
