# PatchRelay

语言: [English](README.md) | 简体中文

PatchRelay 是一个面向智能体编码任务的本地执行中继。它接收来自 OpenClaw 或其他网关的编码请求，将任务分发给本地编码 worker（如 Claude Code 或 Codex），并返回任务状态、日志、diff、测试结果和最终产物。

**当前状态**: ✅ **生产就绪 MVP** — 完整的端到端链路已运行，并通过生产级任务验证。

**🚀 [快速开始指南 →](USAGE.md)** | 一键启动：`cd PatchRelay-tui\server && .\start.ps1`

---

## 已验证的集成链路

```text
用户（OpenClaw Dashboard）
  ↓
OpenClaw Gateway（端口 19001）
  ↓
PatchRelay OpenClaw 插件（patchrelay_submit_task 工具）
  ↓
PatchRelay 服务器（端口 8787，HTTP API）
  ↓
任务队列（串行，隔离的 Git worktrees）
  ↓
Claude Code / Codex Worker（非交互，完整权限）
  ↓
产物（diff、日志、变更文件、测试结果）
  ↓
OpenClaw Dashboard（结果展示）
  ↓
PatchRelay TUI 监控器（实时任务追踪）
```

**设计原则：**
- OpenClaw 处理用户交互、聊天网关和结果展示
- PatchRelay 管理任务执行、Git 隔离和 worker 编排
- Claude Code（或 Codex）执行实际的代码修改
- 每个任务在独立的 Git worktree 中运行，分支名为 `patchrelay/task-<id>`

---

## PatchRelay 的功能

- ✅ 接收来自 OpenClaw Gateway 或直接 HTTP API 调用的编码任务
- ✅ 创建隔离的 Git worktrees（每个任务一个，自动清理）
- ✅ 将任务分发给可配置的 workers：`fake`（测试）、`claude`（Claude Code）、`codex`（Codex CLI）
- ✅ Worker 执行后运行可配置的测试 profiles
- ✅ 收集产物：统一 diff、变更文件、stdout/stderr、测试结果
- ✅ 提供 HTTP API 用于任务提交、状态查询、取消
- ✅ 提供实时 TUI 仪表盘，带实时日志和 diff 查看器
- ✅ 支持一键启动所有服务（Gateway、Server、TUI、Dashboard）

---

## PatchRelay 不做什么

- ❌ 不重建 IM 网关或聊天平台
- ❌ 不从零实现完整的编码 agent
- ❌ 不要求 OpenClaw 直接执行 shell 命令
- ❌ 不自动推送 Git 变更（需要手动审查）
- ❌ 不（尚未）提供生产级的集群、分布式队列或 worker 池

云端 SaaS 演进计划请参见 [ARCHITECTURE_ROADMAP.md](ARCHITECTURE_ROADMAP.md)。

---

## 当前功能

**MVP 已完成：**

| 组件 | 状态 | 说明 |
|------|------|------|
| **一键启动** | ✅ | `start.ps1` 启动 Gateway、Server、TUI、Dashboard |
| **OpenClaw 插件** | ✅ | 工具：`patchrelay_submit_task`、`patchrelay_get_task`、`patchrelay_cancel_task` |
| **Claude Code worker** | ✅ | 完整权限（`--dangerously-skip-permissions`），非交互模式 |
| **Codex worker** | ✅ | JSON 输出模式，结构化结果 |
| **Git worktree 隔离** | ✅ | 分支 `patchrelay/task-<id>`，自动创建和清理 |
| **TUI 监控器** | ✅ | 仪表盘、任务列表、实时日志、diff 查看器、产物展示 |
| **HTTP API** | ✅ | `/tasks`（提交、列表、获取、取消）、`/health`、`/a2a/agent-card` |
| **CLI 工具集** | ✅ | `init`、`doctor`、`smoke`、`submit`、`tasks`、`get`、`cancel`、`cleanup`、`runtime`、`openclaw apply` |
| **测试运行器** | ✅ | 可配置 profiles，超时和通过/失败检测 |
| **生产验证** | ✅ | 成功执行生产级编码任务 |

**已知限制（MVP 范围）：**
- 串行任务队列（一次一个任务）
- 单仓库支持
- 无分布式 worker 池
- 无高可用或故障转移
- 手动清理旧 worktrees（或使用 `patchrelay cleanup`）

---

## 仓库结构

```text
PatchRelay/                          # 文档根目录
|-- README.md                        # 英文版
|-- README.zh-CN.md                  # 本文件（中文版）
|-- USAGE.md                         # 快速开始和日常使用指南
|-- ARCHITECTURE_ROADMAP.md          # 架构演进路线图（Phase 1: 本地，Phase 2: 云端 SaaS）
|-- prd.md                           # 产品需求文档
|
|-- PatchRelay-tui/                  # 主项目目录
    |-- server/                      # Python PatchRelay Core API 和 CLI
    |   |-- src/patchrelay/          # 源代码
    |   |   |-- cli.py               # CLI 入口（基于 Typer）
    |   |   |-- app.py               # FastAPI 服务器
    |   |   |-- tasks.py             # 任务生命周期管理
    |   |   |-- workers.py           # Worker 适配器（fake、claude、codex）
    |   |   |-- git_workspace.py    # Git worktree 管理
    |   |   |-- test_runner.py      # 测试 profile 执行
    |   |   |-- task_store.py       # SQLite 任务持久化
    |   |   |-- tui/                 # TUI 应用（基于 Textual）
    |   |       |-- app.py           # 仪表盘入口
    |   |       |-- screens/         # 仪表盘、任务详情、提交、设置向导
    |   |       |-- widgets/         # 任务表格、实时日志、diff 查看器、状态徽章
    |   |-- tests/                   # Pytest 测试套件（80+ 测试）
    |   |-- start.ps1                # 一键启动（Gateway + Server + TUI + Dashboard）
    |   |-- stop.ps1                 # 停止所有服务
    |   |-- patchrelay.yaml          # 服务器配置（由 `patchrelay init` 生成）
    |
    |-- plugins/openclaw/            # OpenClaw 工具插件（TypeScript）
        |-- src/                     # 源代码
        |   |-- index.ts             # 插件入口
        |   |-- tools.ts             # 工具定义（submit_task、get_task、cancel_task）
        |   |-- client.ts            # HTTP 客户端
        |-- dist/                    # 构建后的插件（JavaScript）
        |-- package.json             # npm 包定义
```

---

## 环境要求

**平台：**
- Windows 10/11（主要平台，已测试）
- macOS / Linux（未测试但应该可以工作）

**依赖：**
- Git
- Python 3.10+
- `uv`（Python 包管理器）
- Node.js 22+
- npm
- **OpenClaw 2026.6.1+**（用于网关集成）
- **Claude Code CLI**（`claude` worker 需要）
- **Codex CLI**（`codex` worker 需要）

**验证已安装的工具：**

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

## 快速设置

### 1. 克隆并安装依赖

```powershell
# 导航到项目目录
cd path\to\PatchRelay\PatchRelay-tui

# 安装 Python 服务器依赖
cd server
uv sync --extra dev

# 安装并构建 OpenClaw 插件
cd ..\plugins\openclaw
npm install
npm run build
npm run plugin:validate
```

### 2. 初始化配置

```powershell
cd ..\..\server
uv run patchrelay init
```

这将创建 `patchrelay.yaml`，包含：
- 仓库路径（默认：父目录）
- 基础分支（默认：`main`）
- 服务器 token（自动生成）
- Worker 命令（自动检测：`claude`、`codex`）
- 测试 profile（默认：打印 "tests ok"）

### 3. 安装 OpenClaw 插件

```powershell
cd ..\plugins\openclaw
openclaw plugins link .

# 验证
openclaw plugins list | Select-String "patchrelay"
```

应用插件配置到 OpenClaw：

```powershell
cd ..\..\server
uv run patchrelay openclaw apply --config .\patchrelay.yaml --apply
```

或手动编辑 `~/.config/openclaw/config.json`：

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

### 4. 运行诊断

```powershell
# 检查配置和依赖
uv run patchrelay doctor --config .\patchrelay.yaml

# 使用 fake worker 进行冒烟测试
uv run patchrelay smoke --config .\patchrelay.yaml --worker fake
```

### 5. 启动所有服务

```powershell
.\start.ps1
```

等待约 30 秒让所有服务启动。你会看到 3 个 PowerShell 窗口 + 浏览器：
- OpenClaw Gateway（端口 19001）
- PatchRelay Server（端口 8787）
- PatchRelay TUI 监控器
- OpenClaw Dashboard（浏览器）

**详细使用指南请参见 [USAGE.md](USAGE.md)。**

---

## CLI 参考

`patchrelay` CLI 提供以下命令：

| 命令 | 用途 |
|------|------|
| `serve` | 运行 PatchRelay HTTP 服务器（uvicorn，端口 8787）|
| `ui` | 启动 TUI 仪表盘 |
| `init` | 生成 `patchrelay.yaml` 配置 |
| `doctor` | 检查配置和依赖 |
| `smoke` | 提交测试任务并验证完整链路 |
| `submit <instruction>` | 通过 CLI 提交编码任务 |
| `tasks` | 列出所有任务 |
| `get <task_id>` | 获取任务详情和产物 |
| `cancel <task_id>` | 取消运行中的任务 |
| `wait <task_id>` | 等待任务完成 |
| `logs <task_id>` | 打印原始 worker 日志 |
| `cleanup` | 删除旧的 worktrees 和分支 |
| `runtime start` | 将 PatchRelay 和 OpenClaw Gateway 作为后台服务启动 |
| `runtime stop` | 停止后台服务 |
| `runtime status` | 检查运行时服务状态 |
| `openclaw apply` | 将 PatchRelay 配置应用到 OpenClaw 插件设置 |

**示例：**

```powershell
# 提交任务并等待完成
uv run patchrelay submit "在 README.md 中添加使用示例" --worker claude --wait

# 列出任务
uv run patchrelay tasks --token <your-token>

# 获取任务详情
uv run patchrelay get task-abc123 --token <your-token>

# 清理旧 worktrees
uv run patchrelay cleanup --config .\patchrelay.yaml --force
```

---

## HTTP API

基础 URL：`http://127.0.0.1:8787`

认证：`Authorization: Bearer <token>`（来自 `patchrelay.yaml`）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/health` | GET | 健康检查（版本、运行时间）|
| `/a2a/agent-card` | GET | A2A agent 能力卡（公开，无需认证）|
| `/tasks` | POST | 提交新任务 |
| `/tasks` | GET | 列出所有任务 |
| `/tasks/{task_id}` | GET | 获取任务详情和产物 |
| `/tasks/{task_id}:cancel` | POST | 取消运行中的任务 |

**提交任务示例：**

```bash
curl -X POST http://127.0.0.1:8787/tasks \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "为登录函数添加错误处理",
    "worker": "claude",
    "test_profile": "default"
  }'
```

---

## 配置

`patchrelay.yaml` 结构：

```yaml
server:
  host: 127.0.0.1
  port: 8787
  token: <自动生成的安全 token>

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
  task_timeout_seconds: 7200       # 2 小时
  worktree_retention_days: 7
```

---

## Worker 详情

### Fake Worker
- 内置测试 worker
- 写入一个虚拟的 `FAKE_CHANGE.txt` 文件
- 总是成功（用于测试链路）

### Claude Worker
- 启动 Claude Code CLI，使用 `--dangerously-skip-permissions`（完整非交互模式）
- 标志：`-p`、`--output-format json`、`--disable-slash-commands`、`--no-session-persistence`
- 可以执行 Bash 命令、读写文件，无权限提示

### Codex Worker
- 启动 Codex CLI，使用 `exec --json`
- 结构化 JSON 输出，包含任务结果

---

## Git 工作流

1. **任务提交** → 服务器创建分支 `patchrelay/task-<id>`
2. **Worktree 创建** → `.patchrelay/worktrees/<id>/`
3. **Worker 执行** → 在 worktree 中修改文件
4. **运行测试** → 执行配置的测试 profile
5. **收集产物** → diff、变更文件、日志、测试结果
6. **任务完成** → Worktree 保留供审查
7. **手动审查** → 用户在 TUI 中或通过 `patchrelay get` 检查 diff
8. **手动合并** → 用户满意后合并分支（无自动推送）
9. **清理** → `patchrelay cleanup` 删除旧 worktrees

---

## 开发

### 运行测试

```powershell
cd PatchRelay-tui\server
uv run pytest                    # 运行所有测试
uv run pytest -v                 # 详细输出
uv run pytest tests/test_tasks.py  # 特定文件
```

### 运行插件测试

```powershell
cd PatchRelay-tui\plugins\openclaw
npm test
npm run plugin:validate
```

---

## 故障排除

### 端口已被占用

```powershell
# 停止所有服务
.\stop.ps1

# 验证端口已释放
netstat -ano | findstr ":8787"
netstat -ano | findstr ":19001"
```

### OpenClaw 插件未加载

```powershell
# 验证插件已链接
openclaw plugins list | Select-String "patchrelay"

# 如需重新链接
cd ..\plugins\openclaw
openclaw plugins link .

# 重启 OpenClaw Gateway
.\stop.ps1
.\start.ps1
```

### Worker 未找到

```powershell
# 检查 worker 命令
claude --version
codex --version

# 如果路径不同，更新 patchrelay.yaml
```

---

## 架构路线图

**Phase 1（当前）：本地部署**
- 单节点执行
- 串行任务队列
- SQLite 持久化
- Git worktree 隔离
- 目标：10-50 并发任务

**Phase 2（计划中）：云端 SaaS**
- 多租户架构
- 分布式 worker 池
- Java Gateway 支持高并发
- Local agent 保护代码安全
- 目标：1000+ 并发任务

详见 [ARCHITECTURE_ROADMAP.md](ARCHITECTURE_ROADMAP.md)。

---

## 文档

- **[USAGE.md](USAGE.md)** — 快速开始和日常使用
- **[prd.md](prd.md)** — 产品需求
- **[ARCHITECTURE_ROADMAP.md](ARCHITECTURE_ROADMAP.md)** — 演进路线图

---

## 许可证

（在此添加你的许可证）

---

**享受使用 PatchRelay！** 🚀

如有问题，请参阅文档或运行 `uv run patchrelay doctor`。
