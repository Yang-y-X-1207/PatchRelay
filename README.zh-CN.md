# PatchRelay

语言：[English](README.md) | 简体中文

PatchRelay 是**两个编码 Agent 之间的桥**。你选一对：**Agent1**（你直接对话的前端 Agent）和 **Agent2**（被委派执行实际编码工作的一方）。PatchRelay 把任务中继给 Agent2，隔离到 Git worktree，运行你的测试，然后返回状态、日志、diff、测试结果和 artifacts。

- 第一次来？先读图文介绍：[INTRODUCTION.zh-CN.md](INTRODUCTION.zh-CN.md)。
- 想马上跑起来？按 Agent 组合分场景的快速上手：[USAGE.zh-CN.md](USAGE.zh-CN.md)。

## 当前阶段

PatchRelay 当前处于 **基本可用 MVP** 阶段。单机中继闭环已经实现并在本地验证。放在前端的是哪个 Agent，决定了拓扑：

```text
转发（Agent1 = OpenClaw）：
  OpenClaw 面板  ->  PatchRelay  ->  Claude 或 Codex  ->  git worktree + 测试
    （你对话）                          (Agent2)

乒乓（Agent1 = Claude 或 Codex）：
  你 -> 桌面 Claude/Codex -> PatchRelay -> 另一个 Agent -> git worktree + 测试
   ^        (Agent1)                        (Agent2)             |
   +--------- review <-- diff / 测试 <-------------------------------+
```

| Agent1 → Agent2 | 拓扑 | 状态 |
|---|---|---|
| OpenClaw → Claude / Codex | 转发：单向委派 | 已验证 |
| Claude ↔ Codex（任一在前端） | 乒乓：桌面会话逐跳接力 | 接力已验证；用 `launch.ps1` 启动 |

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
- 多 Agent 接力：一个 worker 可通过 `.patchrelay/handoff.json` 哨兵把任务交棒给另一个 worker（乒乓），并有可配置的深度守卫，接力链不会无限循环。
- 桌面 Agent1 模式：前端的 Claude/Codex 会话通过 `patchrelay` CLI 把编码工作委派给另一个 Agent（指令约定在 `server/agent1/`）。
- 柔性 `timed_out` 结果：worker 卡住但留下有效 diff 时会保留它（并照常跑测试），不再当作纯失败丢弃；独立、更短的 `worker_timeout_seconds`。
- CLI：init、setup、doctor、runtime start/status/stop、smoke、submit、wait、logs、tasks、cancel、cleanup。
- Textual 全屏 TUI：任务 dashboard、筛选、任务详情、artifact 预览、新任务提交、setup wizard、runtime 控制、smoke test、自动刷新和快捷键。
- Windows PowerShell 启动器：`server/launch.ps1`（交互式 Agent1/Agent2 选择器），以及 `server/start.ps1` / `server/stop.ps1` 用于全栈启动/停止。

## 尚未实现

- 分布式任务队列或多 worker 池。
- 高可用控制面。
- 多仓库 registry 和按仓库划分的权限模型。
- 默认自动 commit、push 或创建 PR。
- 云端 relay 或反向隧道模式。
- 生产级认证、审计、限流和租户能力。
- Java 控制面微服务。该部分仍是后续架构规划，等 Python 本地闭环稳定后再引入。

## 快速启动

面向用户的快速启动指南在 [USAGE.md](USAGE.md)（[中文版](USAGE.zh-CN.md)），按 Agent 组合分场景。它覆盖：

- 安装依赖
- 选择 Agent1/Agent2 并用 `server/launch.ps1` 启动
- 四种组合（OpenClaw→Claude、OpenClaw→Codex、Claude↔Codex）
- 提交任务并在 TUI 里查看进度
- 使用 `server/stop.ps1` 停止服务
- 常见本地问题排查

最短启动方式 —— 一条命令，选你的两个 Agent：

```powershell
cd C:\path\to\PatchRelay\server
.\launch.ps1
```

`launch.ps1` 会问谁是 Agent1、谁是 Agent2，然后只启动这一对需要的组件。
可以用参数跳过菜单，或只预览不启动：

```powershell
.\launch.ps1 -Agent1 openclaw -Agent2 codex          # 转发全栈
.\launch.ps1 -Agent1 claude   -Agent2 codex          # 桌面乒乓
.\launch.ps1 -Agent1 codex    -Agent2 claude -DryRun # 只打印计划
```

`start.ps1` 仍然保留，用于直接启动 OpenClaw 全栈。完整流程请看 [USAGE.md](USAGE.md)。

## 仓库结构

```text
.
|-- INTRODUCTION.md         # 图文项目介绍（桥心智模型）
|-- README.md               # 项目概览和当前状态
|-- README.zh-CN.md         # 中文 README
|-- USAGE.md                # 按 Agent 组合分场景的快速上手（中英）
|-- prd.md                  # 产品需求和路线说明
|-- ARCHITECTURE_ROADMAP.md # 架构演进说明
|-- server/                 # Python server、CLI、TUI、launch.ps1、agent1/ 指令
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
