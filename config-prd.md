# PatchRelay Config Onboarding PRD

## 1. 背景

PatchRelay 已经完成基础可用 MVP 验证：

```text
OpenClaw Gateway/Dashboard
  -> PatchRelay OpenClaw plugin
  -> PatchRelay server
  -> Claude Code worker
  -> PatchRelay artifacts
  -> OpenClaw result view
```

当前主要问题不是核心链路不可用，而是用户配置成本偏高。用户需要手动理解和配置 `patchrelay.yaml`、token、repo path、base branch、worker、test profile、OpenClaw 插件安装和 Gateway 调用方式。

本 PRD 规划 PatchRelay 配置封装 V1，让用户可以通过少量命令完成本地配置、诊断、smoke test 和 OpenClaw 配置命令生成。

## 2. 目标

首版目标是把用户从“手动编辑 yaml + 手动查错 + 手动拼 OpenClaw 命令”降到：

```cmd
patchrelay init
patchrelay doctor --config .\patchrelay.yaml
patchrelay smoke --worker fake
patchrelay smoke --worker claude
```

V1 覆盖：

- 本地 PatchRelay 配置生成
- 本地配置诊断和修复提示
- PatchRelay 本地 smoke test
- OpenClaw 配置命令生成

V1 不覆盖：

- 不自动修改 OpenClaw 配置
- 不自动启动 OpenClaw Gateway
- 不做 profile 管理
- 不做云同步
- 不做高可用、高可靠、高并发架构改造

## 3. 用户体验

### 3.1 初始化

用户在目标目录运行：

```cmd
patchrelay init
```

交互式生成当前目录下的 `patchrelay.yaml`。

默认值应尽量自动探测：

- 当前目录或父目录中的 Git repo
- 当前 Git 分支
- 可用 worker 命令：`claude`、`codex`
- 默认 worker
- 默认测试命令
- server host 和 port

默认自动生成随机 `server.token`。

如果 `patchrelay.yaml` 已存在：

- 默认拒绝覆盖
- 支持 `--force` 覆盖

初始化完成后输出下一步命令：

```cmd
patchrelay serve --config .\patchrelay.yaml
patchrelay doctor --config .\patchrelay.yaml
patchrelay smoke --worker fake --token <generated-token>
```

### 3.2 诊断

用户运行：

```cmd
patchrelay doctor --config .\patchrelay.yaml
```

`doctor` 保持现有检查项，但失败时增加明确修复建议。

普通输出示例：

```text
[fail] repo: git rev-parse --verify main failed with exit code 128: fatal: Needed a single revision
hint: Base branch 'main' does not exist. Available branches: master. Update repo.base_branch to 'master'.
```

JSON 输出需要增加 `hint` 字段：

```json
{
  "name": "repo",
  "ok": false,
  "message": "git rev-parse --verify main failed...",
  "hint": "Base branch 'main' does not exist. Available branches: master. Update repo.base_branch to 'master'."
}
```

### 3.3 本地 smoke test

用户运行：

```cmd
patchrelay smoke --worker fake --token <token>
patchrelay smoke --worker claude --token <token>
```

`smoke` 只验证 PatchRelay 本地链路，不自动启动 OpenClaw Gateway。

行为：

- 向运行中的 PatchRelay server 提交一个最小任务
- 等待任务完成
- 打印 task id、status、worker、changed files、test status
- 失败时输出明确修复建议

worker 默认任务：

- `fake`: 写入 `fake-change.txt`
- `claude` / `codex`: 修改 README，添加一个短小 smoke section

### 3.4 OpenClaw 配置命令生成

用户运行：

```cmd
patchrelay openclaw --config .\patchrelay.yaml
```

该命令只输出用户应执行的 OpenClaw 命令，不直接执行。

输出内容包括：

- 插件构建和校验命令
- `openclaw plugins install ... --link`
- `openclaw config patch --stdin`
- `openclaw plugins inspect patchrelay --runtime --json`
- Gateway `/tools/invoke` smoke 示例

命令需要从 `patchrelay.yaml` 读取：

- `server.host`
- `server.port`
- `server.token`

由此生成：

```text
baseUrl = http://<server.host>:<server.port>
token = <server.token>
```

## 4. CLI 接口

### 4.1 `patchrelay init`

```cmd
patchrelay init --config patchrelay.yaml --force
```

参数：

- `--config`: 输出配置文件路径，默认 `patchrelay.yaml`
- `--force`: 配置文件已存在时允许覆盖

V1 不实现：

- `--yes`
- `--repo-path`
- `--base-branch`
- `--worker`
- `--test-command`
- `--token`

这些放到 V1.1。

### 4.2 `patchrelay smoke`

```cmd
patchrelay smoke --config patchrelay.yaml --worker fake --token <token>
```

参数：

- `--config`: 配置文件路径，默认 `patchrelay.yaml`
- `--worker`: `fake|claude|codex`
- `--token`: PatchRelay bearer token
- `--url`: PatchRelay server URL，默认从配置推导
- `--timeout`: 等待任务完成的超时时间

### 4.3 `patchrelay openclaw`

```cmd
patchrelay openclaw --config patchrelay.yaml
```

参数：

- `--config`: 配置文件路径，默认 `patchrelay.yaml`

行为：

- 读取配置
- 打印 OpenClaw 配置命令
- 不执行任何 OpenClaw 命令

## 5. 配置模型

V1 不新增配置 schema，继续使用现有结构：

```yaml
server:
  host: 127.0.0.1
  port: 8787
  token: <generated-token>

repo:
  path: C:/path/to/repo
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

## 6. Doctor 修复提示要求

`doctor` 需要覆盖以下常见错误提示：

- `repo.path` 不存在
- `repo.path` 不是 Git repo
- `repo.base_branch` 不存在
- `git` 不可用
- `worker.claude_command` 不存在
- `worker.codex_command` 不存在
- `tests` 缺少 `default`
- `tests.default.command` 为空或命令不可用
- token 为空或配置解析失败

提示必须满足：

- 明确指出失败原因
- 给出下一步修复动作
- 能在普通输出和 JSON 输出中获取

## 7. Test Plan

### 7.1 `init`

- 无配置文件时生成有效 `patchrelay.yaml`
- 已存在配置时不覆盖
- `--force` 时覆盖
- Git repo 中能探测当前分支
- 非 Git 目录能生成配置，但 `doctor` 给出 repo 修复提示
- 生成 token 非空且不是固定默认值

### 7.2 `doctor`

- repo ok 时通过
- base branch 不存在时返回 fail + 可用分支 hint
- worker 命令不存在时返回 fail + 修复 hint
- config 解析失败时返回 fail + 修复 hint
- `--json` 包含 `hint`

### 7.3 `smoke`

- fake worker smoke completed
- claude worker 命令不可用时失败信息清晰
- server 未启动时提示先运行 `patchrelay serve`
- token 错误时提示检查 `server.token` 或 `--token`
- 超时时提示任务 id 和查询命令

### 7.4 `openclaw`

- 输出命令包含正确 plugin 路径、baseUrl、token
- 不执行任何 OpenClaw 命令
- token 在普通输出中可显示，因为用户需要复制
- JSON 输出暂不提供

## 8. Later Optimization Roadmap

### V1.1: 非交互 / 脚本化

- 增加 `patchrelay init --yes`
- 增加 `--repo-path`
- 增加 `--base-branch`
- 增加 `--worker`
- 增加 `--test-command`
- 增加 `--token`
- 适合 CI、文档示例和自动化安装脚本

### V1.2: 本地 profile

- 支持 `~/.patchrelay/profiles/<name>.yaml`
- 新增 `patchrelay profile list`
- 新增 `patchrelay profile create`
- 新增 `patchrelay profile use`
- 支持多仓库、多 worker、多 OpenClaw 环境切换

### V1.3: OpenClaw 半自动配置

- 新增 `patchrelay openclaw apply`
- 自动运行 `openclaw plugins install`
- 自动运行 `openclaw config patch`
- 默认 dry-run
- 用户显式加 `--apply` 才真正修改 OpenClaw 配置

### V1.4: Gateway smoke

- 新增 `patchrelay smoke --via openclaw`
- 可选启动 OpenClaw Gateway
- 调用 `/tools/invoke`
- 验证完整链路：

```text
OpenClaw Gateway -> PatchRelay -> Claude Code -> OpenClaw
```

### V1.5: 可视化 / 桌面体验

- 输出可点击 Dashboard URL
- 提供本地配置状态页或简易 Web UI
- 展示当前 repo、worker、token 状态
- 展示最近任务和失败修复建议

### V2: 可靠性和规模化

- 多 worker 并发队列
- 任务重试
- 超时策略
- 失败恢复
- 更强审计日志
- artifact 保留策略
- 多 repo workspace
- 为后续高可用、高可靠、高并发做接口和配置铺垫

### V3: 可选云同步

- 只同步非敏感配置模板
- token、API key、私有路径留在本地
- 云端作为可选 Config Sync
- 云服务不成为 PatchRelay 核心依赖

## 9. Assumptions

- 首版配置文件只写当前目录 `patchrelay.yaml`
- 首版 token 默认自动生成并写入本地 yaml
- 首版 smoke 只验证 PatchRelay 本地链路
- OpenClaw 配置首版只生成命令，不自动修改用户环境
- Profile、云同步、自动 Gateway smoke 放到后续阶段
