# PatchRelay 快速上手 —— 按 Agent 组合分场景

语言：[English](USAGE.md) | 简体中文

PatchRelay 是**两个编码 Agent 之间的桥**。你选一对：

- **Agent1** —— 你直接对话的前端 Agent。
- **Agent2** —— 被委派的执行端，在隔离的 Git worktree 中跑实际编码工作，
  然后返回状态、diff、日志和测试结果。

启动器会根据你选的这一对，自动决定两者**怎么连**：

| Agent1 → Agent2 | 拓扑 | 体感 |
|---|---|---|
| `openclaw` → `claude` / `codex` | **转发** | 你在 OpenClaw 面板里对话；PatchRelay 把每个编码任务转发给 Agent2。 |
| `claude` / `codex` → 另一个 | **乒乓** | 桌面上的 Claude/Codex 会话就是你的前端；它把任务交给 Agent2 并 review 结果，一跳接一跳。 |

## 一条命令

```powershell
cd C:\path\to\PatchRelay\server
.\launch.ps1
```

`launch.ps1` 问两个问题——*谁是 Agent1？* 和 *谁是 Agent2？*——
然后只启动这一对需要的组件。想跳过菜单：

```powershell
.\launch.ps1 -Agent1 openclaw -Agent2 codex     # 转发
.\launch.ps1 -Agent1 claude   -Agent2 codex     # 乒乓
.\launch.ps1 -Agent1 codex    -Agent2 claude -DryRun   # 只打印计划，不启动任何东西
```

前置条件（一次性）：一份可用的 `patchrelay.yaml`。如果还没有：

```powershell
uv run patchrelay setup --config .\patchrelay.yaml --yes
```

---

## 场景 A —— OpenClaw → Claude（转发）

你在浏览器面板里跟 OpenClaw 对话；Claude Code 执行改动。

```powershell
.\launch.ps1 -Agent1 openclaw -Agent2 claude
```

这会启动全栈（OpenClaw 网关 + PatchRelay Server + TUI + 面板），
并把 OpenClaw 的默认 worker 指向 Claude。

1. 等四个窗口/浏览器起来（约 30 秒）。
2. 在面板里提一个编码需求：
   `"给 TaskStore 类加一个 list_by_status 方法，并让测试通过。"`
3. OpenClaw 自动调用 `patchrelay_submit_task`；Claude 在隔离 worktree 里执行。
4. 在 **TUI** 窗口看进度；在那里或面板回复里读 diff / 测试结果。

## 场景 B —— OpenClaw → Codex（转发）

和 A 一样，只是把执行端换成 Codex。

```powershell
.\launch.ps1 -Agent1 openclaw -Agent2 codex
```

其余步骤与场景 A 完全相同。

## 场景 C —— Claude → Codex（乒乓）

**桌面上的 Claude** 会话是你的前端。你跟它对话；它把实现委派给 Codex 并 review 结果。

```powershell
.\launch.ps1 -Agent1 claude -Agent2 codex
```

这会启动 PatchRelay Server + TUI，然后打开一个作为 Agent1 接好线的 Claude 会话
（已设好 `PATCHRELAY_URL` / `PATCHRELAY_TOKEN` / `PATCHRELAY_PARTNER=codex`，
Agent1 契约通过 `--append-system-prompt-file` 注入）。

1. 在 Claude 窗口里描述工作：
   `"在 calc.py 里设计一个小计算器模块——add/subtract/multiply/divide 带 docstring，然后让它被实现并测试。"`
2. Claude 把它转成一份 brief 并委派：
   `patchrelay submit "<brief>" --worker codex --wait`。
3. Codex 在隔离分支上执行；Claude 读 diff/测试、review，然后要么汇报、
   要么改进 brief 并委派下一跳。
4. 每一跳都能在 **TUI** 里监控。

## 场景 D —— Codex → Claude（乒乓）

C 的镜像：**桌面上的 Codex** 会话是前端，委派给 Claude。

```powershell
.\launch.ps1 -Agent1 codex -Agent2 claude
```

Codex 启动时会带一个初始 prompt，让它读自己的 Agent1 契约
（`server/agent1/codex-agent1.md`），并通过 `patchrelay` CLI 把编码工作转给 Claude。

---

## 停止

```powershell
.\stop.ps1
```

或直接关窗口。乒乓模式下，关掉桌面 Agent1 窗口就结束你的前端会话；
`.\stop.ps1` 停掉 Server（以及正在运行的网关）。

## 你可能看到的 worker 结果

- **completed** —— worker 完成，且测试 profile 通过。
- **failed** —— worker 非零退出，或测试失败。diff 仍会被捕获。
- **timed_out** —— worker 撞到墙钟上限（`limits.worker_timeout_seconds`，默认 30 分钟）。
  如果它留下了改动，diff 会被保留、测试照常跑——不会被当成纯失败丢弃。

## 排障

**端口被占用** —— `.\stop.ps1`，等几秒，再启动。

**Agent1 窗口连不上 PatchRelay** —— 确认 Server 窗口在 8787 端口起着，
且 `patchrelay.yaml` 里有真实的 `server.token`。Agent1 会话从环境变量读
`PATCHRELAY_URL` / `PATCHRELAY_TOKEN`；这些由启动器替你设好。

**OpenClaw 看不到工具（转发模式）** —— 启动器会委派给 `start.ps1`，
它会把插件/skill/工具和网关配置对齐。若工具仍不出现，运行
`uv run patchrelay openclaw apply --config .\patchrelay.yaml --apply`。

**换目标仓库或测试命令** —— 编辑 `patchrelay.yaml`：

```yaml
repo:
  path: C:\path\to\your\project
  base_branch: main
tests:
  default:
    command: ["python", "-m", "pytest"]   # 或 ["npm", "test"]、["mvn", "test"]
```

## 常用命令

```powershell
uv run patchrelay runtime status --config .\patchrelay.yaml   # 服务状态
uv run patchrelay tasks --token <token>                        # 任务列表
uv run patchrelay logs <task-id> --token <token>               # 任务时间线
uv run patchrelay cleanup --config .\patchrelay.yaml --force   # 清理 worktree/分支
```
