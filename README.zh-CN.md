# PatchRelay

语言：[English](README.md) | 简体中文

PatchRelay 是一个面向 Agent 编码任务的本地执行中继。它接收来自 OpenClaw 或其他网关的编码请求，把任务交给本地编码 worker，例如 Claude Code 或 Codex，然后返回任务状态、日志、diff、测试结果和 artifacts。

如果你想直接启动和测试，请先看快速启动指南：[USAGE.md](USAGE.md)。

## 当前阶段

PatchRelay 当前处于 **基本可用 MVP** 阶段。单机执行闭环已经实现，并且已经在本地验证：

```text
OpenClaw Dashboard/Gateway
  -> PatchRelay OpenClaw 插件
  -> PatchRelay Python server
  -> Claude Code 或 Codex worker
  -> Git worktree、测试、artifacts
  -> OpenClaw 结果展示或 PatchRelay TUI
```

这还不是生产级高可用系统。当前重点是把本地闭环跑稳定：提交编码任务，隔离到 Git worktree，运行配置好的 worker，收集 artifacts，然后查看结果。

## 已实现

- Python FastAPI PatchRelay server，任务 API 使用 bearer token 保护。
- 类 A2A endpoint：health、agent card、message send/stream、task list/get/events/cancel。
- 基于 SQLite 的本地任务持久化。
- 串行任务队列：当前 MVP 一次只执行一个任务。
- 每个任务独立 Git branch 和 worktree。
- `fake`、`claude`、`codex` worker adapter。
- worker 执行后运行可配置 test profile。
- artifact 收集：summary、changed files、diff、worker logs、test output。
- OpenClaw TypeScript 插件，暴露 `patchrelay_submit_task`、`patchrelay_get_task`、`patchrelay_cancel_task`。
- OpenClaw 插件安装和配置辅助命令。
- CLI：init、setup、doctor、runtime start/status/stop、smoke、submit、wait、logs、tasks、cancel、cleanup。
- Textual 全屏 TUI：任务 dashboard、筛选、任务详情、artifact 预览、新任务提交、setup wizard、runtime 控制、smoke test、自动刷新和快捷键。
- Windows PowerShell `server/start.ps1` 和 `server/stop.ps1`，用于本地一键启动和停止。

## 尚未实现

- 分布式任务队列或多 worker 池。
- 高可用控制面。
- 多仓库 registry 和按仓库划分的权限模型。
- 默认自动 commit、push 或创建 PR。
- 云端 relay 或反向隧道模式。
- 生产级认证、审计、限流和租户能力。
- Java 控制面微服务。该部分仍是后续架构规划，等 Python 本地闭环稳定后再引入。

## 快速启动

面向用户的快速启动指南在 [USAGE.md](USAGE.md)。它覆盖：

- 安装依赖
- 运行 `server/start.ps1`
- 启动 OpenClaw Gateway、PatchRelay Server、PatchRelay TUI 和 OpenClaw Dashboard
- 从 OpenClaw 提交任务
- 在 TUI 里查看任务进度
- 使用 `server/stop.ps1` 停止服务
- 常见本地问题排查

最短启动方式：

```powershell
cd C:\path\to\PatchRelay\server
.\start.ps1
```

然后等待 Gateway、server、TUI 和浏览器 dashboard 启动完成。完整流程请看 [USAGE.md](USAGE.md)。

## 仓库结构

```text
.
|-- README.md               # 项目概览和当前状态
|-- README.zh-CN.md         # 中文 README
|-- USAGE.md                # 快速启动和本地测试指南
|-- prd.md                  # 产品需求和路线说明
|-- ARCHITECTURE_ROADMAP.md # 架构演进说明
|-- server/                 # Python PatchRelay server、CLI、TUI、脚本
|-- plugins/openclaw/       # OpenClaw TypeScript 插件
|-- docs/                   # 其他规划和产品文档
```

## 环境要求

推荐本地环境：

- Windows 10/11
- Git
- Python 3.10+
- `uv`
- Node.js 22+
- npm
- OpenClaw 2026.6.1 或更新版本
- Claude Code CLI，用于 Claude worker
- Codex CLI，用于 Codex worker

检查工具：

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

## 安装

从仓库根目录执行：

```powershell
cd .\server
uv sync --extra dev --extra tui

cd ..\plugins\openclaw
npm install
npm run build
```

生成或修复本地配置：

```powershell
cd ..\..\server
uv run patchrelay setup --config .\patchrelay.yaml
```

使用默认选择进行非交互式配置：

```powershell
uv run patchrelay setup --config .\patchrelay.yaml --yes
```

## 常用命令

运行诊断：

```powershell
uv run patchrelay doctor --config .\patchrelay.yaml
uv run patchrelay setup verify --config .\patchrelay.yaml
```

启动、查看、停止受管理的 runtime：

```powershell
uv run patchrelay runtime start --config .\patchrelay.yaml
uv run patchrelay runtime status --config .\patchrelay.yaml
uv run patchrelay runtime stop --config .\patchrelay.yaml
```

启动 TUI：

```powershell
uv run patchrelay ui --config .\patchrelay.yaml
```

运行本地 smoke test：

```powershell
uv run patchrelay smoke --config .\patchrelay.yaml --worker fake
```

直接向 PatchRelay 提交任务：

```powershell
uv run patchrelay submit "Add a short usage note to README.md" --worker fake --wait --token <patchrelay-token>
```

通过 OpenClaw Gateway 运行 smoke test：

```powershell
uv run patchrelay smoke `
  --config .\patchrelay.yaml `
  --via openclaw `
  --worker fake `
  --gateway-url http://127.0.0.1:19001 `
  --gateway-token openclaw-local-token
```

## OpenClaw 集成

构建并校验插件：

```powershell
cd .\plugins\openclaw
npm run plugin:validate
```

把本地插件安装到 OpenClaw：

```powershell
openclaw plugins install C:\path\to\PatchRelay\plugins\openclaw --link
```

根据 PatchRelay 配置应用 OpenClaw 设置：

```powershell
cd C:\path\to\PatchRelay\server
uv run patchrelay openclaw apply --config .\patchrelay.yaml --apply
openclaw plugins inspect patchrelay --runtime --json
```

OpenClaw 应该暴露：

- `patchrelay_submit_task`
- `patchrelay_get_task`
- `patchrelay_cancel_task`

## API Surface

主要 server endpoints：

- `GET /health`
- `GET /.well-known/agent-card.json`
- `POST /message:send`
- `POST /message:stream`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/events`
- `POST /tasks/{task_id}:cancel`

任务响应包含 status、worker、phase、branch、worktree path、events 和 artifacts。事件时间线可以用 `/tasks/{task_id}/events?after=<sequence>` 分页读取。

## 开发验证

运行 server 测试：

```powershell
cd .\server
uv run pytest
```

运行插件测试：

```powershell
cd .\plugins\openclaw
npm test
npm run plugin:validate
```

## MVP 限制

当前 MVP 刻意保持小范围：

- 先支持一个本地仓库
- 一次只执行一个任务
- 每个任务独立 branch/worktree
- 本地 SQLite 任务持久化
- 通过 `patchrelay cleanup` 手动清理
- 默认不自动 Git push 或创建 PR
- 暂无分布式 worker 池

长期方向是让 Python 专注 Agent 执行链路，后续再引入 Java 控制面服务来承担高并发、高可用、调度、认证和生产运维能力。
