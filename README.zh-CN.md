# PatchRelay

语言：[English](README.md) | 简体中文

PatchRelay 是一个面向 Agent 编码任务的本地远程执行中继。

它运行在开发者本机或可信内网机器上，接收来自 OpenClaw 或其他 A2A 兼容客户端的编码任务，将任务分发给本地编码 worker，例如 Codex 或 Claude Code，并返回任务状态、日志、diff 和测试结果。

## 当前 MVP 方向

PatchRelay 不重建 IM 网关，也不重建完整 Coding Agent。当前 MVP 规划如下：

```text
OpenClaw Gateway
  -> PatchRelay OpenClaw Tool Plugin
  -> PatchRelay Local A2A-compatible Server
  -> Serial Task Queue
  -> Fake Worker first, then Codex / Claude Code adapters
```

当前已经具备一个可运行的 Python Core API、SQLite 任务持久化、fake worker 演示链路、Git worktree 隔离和测试 profile 执行能力。Codex 和 Claude Code adapter 的命令路径已经接入，后续会继续增强真实 worker 的运行体验、审批和交付能力。

## 仓库结构

```text
.
├── MEMORY.md              # 产品记忆和方向记录
├── prd.md                 # 产品需求文档
├── server/                # Python PatchRelay Core
└── plugins/openclaw/      # OpenClaw Tool Plugin spike
```

## 开发规则

- Windows 是当前优先支持的开发环境。
- 重大功能从 `main` 拉 feature 分支开发。
- feature 分支在本地提交后合并回 `main`。
- 合并完成后按当前协作约定自动 push 到远端。
- 推荐使用 `uv` 管理 Python 依赖；代码也兼容标准 `python -m pip` 工作流。

## 文档

- 产品需求文档：[prd.md](prd.md)
- 项目记忆：[MEMORY.md](MEMORY.md)

## 本地演示

当前演示使用 fake worker。它会创建任务分支和 worktree，写入 `fake-change.txt`，运行一个轻量测试 profile，并通过 API/CLI 返回 artifacts。

从仓库根目录进入 server：

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
uv sync --extra dev
Copy-Item .\examples\demo.patchrelay.yaml .\patchrelay.yaml
```

终端 1 启动服务：

```powershell
uv run patchrelay serve --config .\patchrelay.yaml
```

终端 2 提交演示任务：

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay\server
$env:PATCHRELAY_TOKEN="demo-token"
uv run patchrelay doctor --config .\patchrelay.yaml
uv run patchrelay submit "Create a demo fake worker change" --worker fake --wait --token demo-token
uv run patchrelay tasks --token demo-token
```

预期结果：

- 任务状态为 `completed`
- 分支名以 `patchrelay/` 开头
- changed files 包含 `fake-change.txt`
- test status 为 `passed`

检查完成后，先预览将要清理的 PatchRelay 产物：

```powershell
uv run patchrelay cleanup --config .\patchrelay.yaml
```

确认无误后，删除 demo worktree、本地 `patchrelay/*` 临时分支和 `.patchrelay/` 状态目录：

```powershell
uv run patchrelay cleanup --config .\patchrelay.yaml --force
```
