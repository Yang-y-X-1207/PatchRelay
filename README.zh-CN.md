# PatchRelay

语言：[English](README.md) | 简体中文

PatchRelay 是一个面向 Agent 编码任务的本地执行中继。它接收来自 OpenClaw 或其他网关的编码请求，把任务分发给本地编码 worker，例如 Claude Code 或 Codex，然后返回任务状态、日志、diff、测试结果和最终 artifacts。

当前项目阶段是 **基本可用 MVP**。已经验证通过的链路是：

```text
OpenClaw Gateway/Dashboard
  -> PatchRelay OpenClaw 插件
  -> PatchRelay server
  -> Claude Code worker
  -> PatchRelay artifacts
  -> OpenClaw 结果展示
```

在这个设计里，OpenClaw 应该只负责接收用户请求、调用 PatchRelay 工具、展示返回结果。真正执行命令和修改代码的是 PatchRelay 启动的 worker，例如 Claude Code。

## 当前状态

基础三端联调已经验证通过：

- OpenClaw Gateway 可以加载 `patchrelay` 插件。
- OpenClaw Gateway 可以通过 `/tools/invoke` 调用 PatchRelay。
- PatchRelay 可以接收并持久化任务。
- PatchRelay 可以为任务创建 Git 分支和 worktree。
- PatchRelay 可以把 Claude Code 作为真实 coding worker 运行。
- PatchRelay 可以收集 changed files、diff、worker 日志和测试结果。
- OpenClaw 可以通过 `patchrelay_get_task` 取回最终任务结果。

这还不是高可用、高可靠、高并发的生产系统。这些能力是后续阶段的明确目标。当前优先级是把单节点真实执行闭环做清楚、跑稳定。

## PatchRelay 做什么

PatchRelay 是桥接层，不是 OpenClaw 或 Claude Code 的替代品。

- 接收来自 OpenClaw 或 API 客户端的远程编码任务。
- 把请求规范化为简单任务协议。
- 当前 MVP 使用串行队列执行任务。
- 每个任务创建独立 Git 分支和 worktree。
- 把 instruction 分发给指定 worker：`fake`、`claude` 或 `codex`。
- worker 执行完成后运行配置好的 test profile。
- 返回状态、日志、changed files、diff、worker 输出和测试结果。

## PatchRelay 不做什么

- 不重建 IM 网关。
- 不从零实现完整 Coding Agent。
- 不要求 OpenClaw 在目标仓库里直接执行 shell 命令。
- MVP 流程里不会自动 `git push`。
- 目前还没有生产级集群、分布式队列或 worker 池。

如果你的要求是 OpenClaw 永远不要直接改文件，建议把 OpenClaw agent 的可用工具限制为：

- `patchrelay_submit_task`
- `patchrelay_get_task`
- `patchrelay_cancel_task`

不要给该 agent 暴露无关的 shell、exec 或直接代码编辑工具。

## 仓库结构

```text
.
|-- MEMORY.md                # 产品记忆和方向记录
|-- prd.md                   # 产品需求文档
|-- server/                  # Python PatchRelay Core API 和 CLI
|-- plugins/openclaw/        # OpenClaw 工具插件
```

## 环境要求

推荐环境：

- Windows 10/11
- Git
- Python 3.10+
- `uv`
- Node.js 22+
- npm
- OpenClaw 2026.6.1 或更新版本
- Claude Code CLI，如果要使用 Claude worker
- Codex CLI，如果要使用 Codex worker

检查本地工具：

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

## 安装依赖

从仓库根目录开始：

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay
```

安装 PatchRelay server 依赖：

```powershell
cd .\server
uv sync --extra dev
```

安装 OpenClaw 插件依赖：

```powershell
cd ..\plugins\openclaw
npm install
npm run build
```

## PatchRelay 配置

生成 server 配置：

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
uv run patchrelay init --config .\patchrelay.yaml
```

使用只问 yes/no 的引导式配置：

```powershell
uv run patchrelay setup --config .\patchrelay.yaml
```

`patchrelay setup` 会先展示自动探测出的默认值，并且只在写入配置、修复已有配置、运行 doctor、应用 OpenClaw 设置、运行 Gateway smoke test 前询问 yes/no。配置已存在时，setup 会先预览可修复问题，确认后才会写入变更。

演示或脚本化场景可以接受默认 yes/no 选择：

```powershell
uv run patchrelay setup --config .\patchrelay.yaml --yes
```

只检查当前配置状态，不修改任何内容：

```powershell
uv run patchrelay setup status --config .\patchrelay.yaml
```

`setup status` 会检查 config、doctor、PatchRelay `/health` 和 OpenClaw Gateway 工具可达性。

脚本或 CI 场景可以输出同样状态的 JSON：

```powershell
uv run patchrelay setup status --config .\patchrelay.yaml --json
```

预览常见本地配置问题的修复方案：

```powershell
uv run patchrelay setup repair --config .\patchrelay.yaml
```

`setup repair` 可以创建缺失配置、替换空 token 或默认 token、修复 repo/base branch、补齐 worker 命令、补齐默认 test profile 和默认 limits。默认只 dry-run；加 `--apply` 才会写回 YAML：

```powershell
uv run patchrelay setup repair --config .\patchrelay.yaml --apply
```

脚本或 CI 场景也可以输出 repair 计划和结果的 JSON：

```powershell
uv run patchrelay setup repair --config .\patchrelay.yaml --json
```

如果想用一条非破坏性命令同时汇总状态和修复建议：

```powershell
uv run patchrelay setup verify --config .\patchrelay.yaml
```

`setup verify` 会打印状态检查、repair 计划和推荐下一步。需要结构化输出时可以加 `--json`。

配置完成后可以一键启动本地 runtime：

```powershell
uv run patchrelay setup start --config .\patchrelay.yaml
```

该命令会在后台启动 PatchRelay server；如果 `openclaw` 在 PATH 中可用，也会启动 OpenClaw Gateway，并检查配置中的 Codex / Claude CLI 是否可用。Codex 和 Claude 不是常驻服务；PatchRelay 会在每个任务到来时自动启动对应 worker 进程。

查看或停止受管理的 runtime：

```powershell
uv run patchrelay runtime status --config .\patchrelay.yaml
uv run patchrelay runtime stop --config .\patchrelay.yaml
```

需要结构化输出时可以加 `--json`。runtime 状态和日志会写到配置的 repo `state_dir` 下，例如 `.patchrelay\runtime.json` 和 `.patchrelay\runtime\*.log`。

`patchrelay init` 会自动探测当前 Git 仓库、当前分支、可用 worker 命令、默认测试命令，并写入随机本地 bearer token。

脚本化配置时可以显式传入参数：

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

如果你想从示例文件开始，也仍然可以手动复制 `server/examples/patchrelay.yaml`。

示例 `patchrelay.yaml`：

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

关键字段：

- `server.token`：PatchRelay 客户端访问时使用的 bearer token。
- `repo.path`：worker 要修改的目标仓库。
- `repo.base_branch`：任务 worktree 的基准分支。
- `worker.default`：请求使用 `auto` 时的默认 worker。
- `tests.default.command`：worker 执行完成后的测试命令。
- `limits.task_timeout_seconds`：worker 超时时间。

如果只是做轻量演示，可以使用 `server/examples/demo.patchrelay.yaml`；它使用 `fake` worker 和一个简单测试命令。

## 启动 PatchRelay

一键启动本地 runtime：

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
uv run patchrelay runtime start --config .\patchrelay.yaml
```

查看受管理进程和 worker CLI 可用性：

```powershell
uv run patchrelay runtime status --config .\patchrelay.yaml
```

停止 PatchRelay / OpenClaw 受管理进程：

```powershell
uv run patchrelay runtime stop --config .\patchrelay.yaml
```

如果想以前台方式运行 server，仍然可以手动启动：

```powershell
uv run patchrelay serve --config .\patchrelay.yaml
```

期望 runtime / `doctor` 检查通过：

- repo 有效
- git 可用
- 配置的 worker 命令可用
- 存在 `default` test profile

## 本地 CLI 使用

对运行中的 PatchRelay server 执行本地 smoke test：

```powershell
uv run patchrelay smoke --config .\patchrelay.yaml --worker fake
```

提交 fake worker 任务：

```powershell
uv run patchrelay submit "Create a demo fake worker change" --worker fake --wait --token change-me
```

等待任务时跟随打印事件：

```powershell
uv run patchrelay submit "Create a demo fake worker change" --worker fake --wait --token change-me
uv run patchrelay wait <task-id> --follow --token change-me
```

打印任务事件时间线：

```powershell
uv run patchrelay logs <task-id> --token change-me
```

提交 Claude Code 任务：

```powershell
uv run patchrelay submit "Add a short Usage section to README.md" --worker claude --wait --token change-me
```

查看任务列表：

```powershell
uv run patchrelay tasks --token change-me
```

查看原始 JSON：

```powershell
uv run patchrelay tasks --token change-me --json
```

预览清理内容：

```powershell
uv run patchrelay cleanup --config .\patchrelay.yaml
```

删除 PatchRelay worktree、`patchrelay/*` 分支和本地状态：

```powershell
uv run patchrelay cleanup --config .\patchrelay.yaml --force
```

## OpenClaw 集成

根据当前 PatchRelay 配置打印 OpenClaw 设置命令：

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
uv run patchrelay openclaw --config .\patchrelay.yaml
```

预览 OpenClaw 设置步骤：

```powershell
uv run patchrelay openclaw apply --config .\patchrelay.yaml
```

执行 OpenClaw 设置：

```powershell
uv run patchrelay openclaw apply --config .\patchrelay.yaml --apply
```

通过 OpenClaw Gateway 执行 smoke test：

```powershell
uv run patchrelay smoke `
  --config .\patchrelay.yaml `
  --via openclaw `
  --worker fake `
  --gateway-url http://127.0.0.1:19001 `
  --gateway-token openclaw-local-token
```

该命令会通过 Gateway `/tools/invoke` 调用 `patchrelay_submit_task` 和 `patchrelay_get_task`。如果 PatchRelay server 或 OpenClaw Gateway 还没运行，先执行 `patchrelay runtime start`。

构建并校验插件：

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\plugins\openclaw
npm run plugin:validate
```

把本地插件安装到 OpenClaw：

```powershell
openclaw plugins install C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\plugins\openclaw --link
```

配置插件：

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

检查插件运行态：

```powershell
openclaw plugins inspect patchrelay --runtime --json
```

插件应该暴露三个工具：

- `patchrelay_submit_task`
- `patchrelay_get_task`
- `patchrelay_cancel_task`

## OpenClaw Gateway 流程

启动 OpenClaw Gateway：

```powershell
openclaw gateway run --port 19001 --auth token --token openclaw-local-token --bind loopback --force
```

检查 Gateway health：

```powershell
openclaw gateway call health --url ws://127.0.0.1:19001 --token openclaw-local-token --json
```

health 响应里的 `plugins.loaded` 应该包含 `patchrelay`。

通过 OpenClaw Gateway HTTP tools 提交 PatchRelay 任务：

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

通过 OpenClaw Gateway 获取结果：

```powershell
$taskId = "<patchrelay_submit_task 返回的 task id>"
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

期望结果：

- `status` 是 `completed`
- `worker` 是 `claude`
- `artifacts.patchrelay.summary.content.testStatus` 是 `passed`
- `artifacts.patchrelay.diff.content` 包含代码 diff

## OpenClaw Dashboard

打开 Dashboard：

```powershell
openclaw dashboard
```

只打印 URL、不打开浏览器：

```powershell
openclaw dashboard --no-open --yes
```

Dashboard 会连接正在运行的 Gateway。目标使用方式是：

```text
用户请求
  -> OpenClaw Dashboard/Gateway
  -> patchrelay_submit_task
  -> PatchRelay server
  -> Claude Code worker
  -> patchrelay_get_task
  -> Dashboard 展示结果
```

## API 形态

PatchRelay 接收类似 A2A 的请求：

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

主要 server endpoints：

- `GET /health`
- `GET /.well-known/agent-card.json`
- `POST /message:send`
- `POST /message:stream`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/events`
- `POST /tasks/{task_id}:cancel`

任务响应会包含 `eventCount`、`latestEvent` 和最近的 `events`。可以用 `/tasks/{task_id}/events?after=<sequence>` 分页获取新的时间线事件。

## 开发验证

运行 server 测试：

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
uv run pytest
```

运行插件测试：

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\plugins\openclaw
npm test
npm run plugin:validate
```

## MVP 限制

当前 MVP 刻意保持小范围：

- 先支持一个本地仓库
- 串行队列，一次执行一个任务
- 每个任务一个 Git worktree
- 本地 SQLite 任务持久化
- 手动清理
- 默认不自动 Git push
- 暂无分布式 worker 池

后续阶段会继续补高可用、高可靠、高并发能力，但核心契约不变：OpenClaw 负责派发和展示，PatchRelay 负责中继和记录，Claude Code 或其他 worker 负责真正执行。
