# PatchRelay

Language: English | [Simplified Chinese](README.zh-CN.md)

PatchRelay is a local execution relay for agentic coding tasks. It receives coding requests from OpenClaw or another gateway, dispatches them to a local coding worker such as Claude Code or Codex, and returns task status, logs, diffs, test results, and final artifacts.

The current project stage is **basic usable MVP**. The verified path is:

```text
OpenClaw Gateway/Dashboard
  -> PatchRelay OpenClaw plugin
  -> PatchRelay server
  -> Claude Code worker
  -> PatchRelay artifacts
  -> OpenClaw result view
```

In this design, OpenClaw should only receive the user request, invoke PatchRelay tools, and display the returned result. The actual command execution and code modification happen inside the worker launched by PatchRelay, for example Claude Code.

## Current Status

The basic three-end integration has been verified:

- OpenClaw Gateway can load the `patchrelay` plugin.
- OpenClaw Gateway can invoke PatchRelay through `/tools/invoke`.
- PatchRelay can receive and persist tasks.
- PatchRelay can create a task branch and Git worktree.
- PatchRelay can run Claude Code as the real coding worker.
- PatchRelay can collect changed files, diff, worker logs, and test results.
- OpenClaw can fetch the final task result through `patchrelay_get_task`.

This is not yet a high-availability, high-reliability, high-concurrency production system. Those are explicit later-stage goals. The current priority is a clear and stable single-node execution loop.

## What PatchRelay Does

PatchRelay is intentionally a bridge layer, not a replacement for OpenClaw or Claude Code.

- Accepts remote coding tasks from OpenClaw or an API client.
- Normalizes them into a simple task protocol.
- Queues tasks serially in the current MVP.
- Creates an isolated Git branch/worktree per task.
- Dispatches the instruction to a selected worker: `fake`, `claude`, or `codex`.
- Runs a configured test profile after worker execution.
- Returns status, logs, changed files, diff, worker output, and test result.

## What PatchRelay Does Not Do

- It does not rebuild an IM gateway.
- It does not implement a full coding agent from scratch.
- It does not require OpenClaw to execute shell commands in the target repository.
- It does not automatically push Git changes in the MVP flow.
- It does not yet provide production-grade clustering, distributed queues, or worker pools.

If you want to enforce that OpenClaw never edits files directly, configure OpenClaw so the agent only has access to the PatchRelay tools:

- `patchrelay_submit_task`
- `patchrelay_get_task`
- `patchrelay_cancel_task`

Avoid exposing unrelated shell, exec, or direct code-editing tools to that OpenClaw agent.

## Repository Layout

```text
.
|-- MEMORY.md                # Product memory and direction notes
|-- prd.md                   # Product requirements document
|-- server/                  # Python PatchRelay Core API and CLI
|-- plugins/openclaw/        # OpenClaw tool plugin
```

## Requirements

Recommended environment:

- Windows 10/11
- Git
- Python 3.10+
- `uv`
- Node.js 22+
- npm
- OpenClaw 2026.6.1 or newer
- Claude Code CLI if you want the Claude worker
- Codex CLI if you want the Codex worker

Check local tools:

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

## Install Dependencies

From the repository root:

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay
```

Install the PatchRelay server dependencies:

```powershell
cd .\server
uv sync --extra dev
```

Install the OpenClaw plugin dependencies:

```powershell
cd ..\plugins\openclaw
npm install
npm run build
```

## PatchRelay Configuration

Generate a server config:

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
uv run patchrelay init --config .\patchrelay.yaml
```

For a guided yes/no setup:

```powershell
uv run patchrelay setup --config .\patchrelay.yaml
```

`patchrelay setup` prints detected defaults and only asks yes/no questions before writing config, running doctor checks, applying OpenClaw setup, or running a Gateway smoke test.

For demos and scripts, accept the default yes/no choices:

```powershell
uv run patchrelay setup --config .\patchrelay.yaml --yes
```

`patchrelay init` detects the current Git repository, current branch, available worker commands, a default test command, and writes a random local bearer token.

For scripted setup, pass explicit values:

```powershell
uv run patchrelay init `
  --config .\patchrelay.yaml `
  --force `
  --yes `
  --repo-path C:\path\to\your\repo `
  --base-branch main `
  --worker claude `
  --test-command "python -m pytest" `
  --token change-me
```

You can still copy `server/examples/patchrelay.yaml` manually if you want to start from the sample file.

Example `patchrelay.yaml`:

```yaml
server:
  host: 127.0.0.1
  port: 8787
  token: change-me

repo:
  path: C:/path/to/your/repo
  base_branch: main
  state_dir: .patchrelay

worker:
  default: claude
  codex_command: codex
  claude_command: claude

tests:
  default:
    command: ["python", "-m", "pytest"]

limits:
  max_log_bytes: 1048576
  max_diff_bytes: 5242880
  task_timeout_seconds: 3600
```

Important fields:

- `server.token`: bearer token required by PatchRelay clients.
- `repo.path`: target repository that workers will modify.
- `repo.base_branch`: branch used as the base for task worktrees.
- `worker.default`: default worker when the request uses `auto`.
- `tests.default.command`: command run after the worker finishes.
- `limits.task_timeout_seconds`: worker timeout.

For a lightweight demo, use `server/examples/demo.patchrelay.yaml`; it uses the `fake` worker and a simple test command.

## Start PatchRelay

Terminal 1:

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
uv run patchrelay serve --config .\patchrelay.yaml
```

Terminal 2:

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
$env:PATCHRELAY_TOKEN="change-me"
uv run patchrelay doctor --config .\patchrelay.yaml
```

Expected `doctor` checks:

- repo is valid
- git is available
- configured worker commands are available
- `default` test profile exists

## Local CLI Usage

Run a local smoke test against a running PatchRelay server:

```powershell
uv run patchrelay smoke --config .\patchrelay.yaml --worker fake
```

Submit a fake-worker task:

```powershell
uv run patchrelay submit "Create a demo fake worker change" --worker fake --wait --token change-me
```

Submit a Claude Code task:

```powershell
uv run patchrelay submit "Add a short Usage section to README.md" --worker claude --wait --token change-me
```

List tasks:

```powershell
uv run patchrelay tasks --token change-me
```

Fetch raw JSON:

```powershell
uv run patchrelay tasks --token change-me --json
```

Preview cleanup:

```powershell
uv run patchrelay cleanup --config .\patchrelay.yaml
```

Remove PatchRelay worktrees, `patchrelay/*` branches, and local state:

```powershell
uv run patchrelay cleanup --config .\patchrelay.yaml --force
```

## OpenClaw Integration

Print OpenClaw setup commands from the current PatchRelay config:

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
uv run patchrelay openclaw --config .\patchrelay.yaml
```

Preview the OpenClaw setup steps:

```powershell
uv run patchrelay openclaw apply --config .\patchrelay.yaml
```

Apply the OpenClaw setup:

```powershell
uv run patchrelay openclaw apply --config .\patchrelay.yaml --apply
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

This calls `patchrelay_submit_task` and `patchrelay_get_task` through Gateway `/tools/invoke`. PatchRelay server and OpenClaw Gateway must already be running.

Build and validate the plugin:

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\plugins\openclaw
npm run plugin:validate
```

Install the local plugin into OpenClaw:

```powershell
openclaw plugins install C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\plugins\openclaw --link
```

Configure the plugin:

```powershell
@'
{
  plugins: {
    entries: {
      patchrelay: {
        enabled: true,
        config: {
          baseUrl: "http://127.0.0.1:8787",
          token: "change-me"
        }
      }
    }
  }
}
'@ | openclaw config patch --stdin
```

Inspect the plugin runtime:

```powershell
openclaw plugins inspect patchrelay --runtime --json
```

The plugin should expose:

- `patchrelay_submit_task`
- `patchrelay_get_task`
- `patchrelay_cancel_task`

## OpenClaw Gateway Flow

Start the OpenClaw Gateway:

```powershell
openclaw gateway run --port 19001 --auth token --token openclaw-local-token --bind loopback --force
```

Check Gateway health:

```powershell
openclaw gateway call health --url ws://127.0.0.1:19001 --token openclaw-local-token --json
```

The health response should include `patchrelay` in `plugins.loaded`.

Submit a PatchRelay task through OpenClaw Gateway HTTP tools:

```powershell
$body = @{
  name = "patchrelay_submit_task"
  args = @{
    instruction = "Add a short Usage section to README.md"
    worker = "claude"
    testProfile = "default"
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:19001/tools/invoke" `
  -Headers @{ Authorization = "Bearer openclaw-local-token" } `
  -ContentType "application/json" `
  -Body $body
```

Fetch the result through OpenClaw Gateway:

```powershell
$taskId = "<task id returned by patchrelay_submit_task>"
$body = @{
  name = "patchrelay_get_task"
  args = @{ taskId = $taskId }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:19001/tools/invoke" `
  -Headers @{ Authorization = "Bearer openclaw-local-token" } `
  -ContentType "application/json" `
  -Body $body
```

Expected result:

- `status` is `completed`
- `worker` is `claude`
- `artifacts.patchrelay.summary.content.testStatus` is `passed`
- `artifacts.patchrelay.diff.content` contains the code diff

## OpenClaw Dashboard

Open the Dashboard:

```powershell
openclaw dashboard
```

For a non-interactive URL only:

```powershell
openclaw dashboard --no-open --yes
```

The Dashboard talks to the running Gateway. The intended usage is:

```text
User request
  -> OpenClaw Dashboard/Gateway
  -> patchrelay_submit_task
  -> PatchRelay server
  -> Claude Code worker
  -> patchrelay_get_task
  -> Dashboard result
```

## API Shape

PatchRelay accepts an A2A-like request:

```json
{
  "message": {
    "role": "ROLE_USER",
    "parts": [
      { "text": "Add a short Usage section to README.md" }
    ]
  },
  "metadata": {
    "patchrelay": {
      "worker": "claude",
      "testProfile": "default"
    }
  }
}
```

Main server endpoints:

- `GET /health`
- `GET /.well-known/agent-card.json`
- `POST /message:send`
- `POST /message:stream`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}:cancel`

## Development Verification

Run server tests:

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
uv run pytest
```

Run plugin tests:

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\plugins\openclaw
npm test
npm run plugin:validate
```

## MVP Limits

The current MVP intentionally keeps the system small:

- one local repository first
- one task at a time through a serial queue
- branch-per-task Git worktree isolation
- local SQLite task persistence
- manual cleanup
- no automatic Git push by default
- no distributed worker pool yet

Later stages should add high availability, high reliability, and high concurrency without changing the core contract: OpenClaw dispatches and displays; PatchRelay relays and records; Claude Code or another worker executes.
