# 让 Agent1 自动感知并使用 PatchRelay 的方案

## 1. 问题定义

当前链路已经跑通：

```
OpenClaw Dashboard/Gateway (Agent1)
  -> patchrelay_submit_task / patchrelay_get_task / patchrelay_cancel_task
  -> PatchRelay Server
  -> Claude Code / Codex worker (Agent2)
```

三个工具已经通过插件注册到 OpenClaw，Agent1 **能力上**可以调用它们。缺的不是能力，而是**触发意识（perception）**：

- 工具只有极简 `description`（如 "Submit a coding task to PatchRelay."）。
- 没有任何地方告诉 Agent1「遇到编码类任务时，应该优先把活儿委派给 PatchRelay，而不是自己动手或直接回答」。
- 因此除非用户显式提示「用 PatchRelay 做这个」，Agent1 不会主动选用它。

本质是一个**工具可发现性 / 委派策略**问题，而不是配置连通性问题。

## 2. OpenClaw 里可用的几种引导机制对比

我检查了本机 OpenClaw 2026.6.1 的实际能力（`openclaw skills`、`openclaw hooks`、`agents.defaults`、workspace 指令文件），可选机制如下：

| 机制 | 作用方式 | 是否适合本问题 | 代价 |
|------|----------|----------------|------|
| **Skill**（`openclaw skills`） | SKILL.md 的 `description` 常驻注入模型上下文，用于「判断相关性」；命中后再按需加载正文（渐进式披露） | ✅ **最合适**，就是为「能力发现 + 何时使用」设计的 | 极低：常驻的只有一行描述 |
| Workspace 指令文件（`AGENTS.md`/`SOUL.md`/`USER.md`） | 全量常驻进系统提示 | ⚠️ 可做兜底一行提示 | 每轮都吃 token，不可按需，容易膨胀 |
| 工具 `description`（`index.ts`） | 每个工具一句话说明 | ⚠️ 辅助手段 | 太简短，说不清「何时该主动用」 |
| Hooks（`openclaw hooks`） | 事件拦截器，在消息/事件时注入内容 | ❌ 过重、易碎 | 不是为能力发现设计的 |

**关键证据**：OpenClaw 官方自带了一个 `coding-agent` skill，描述就是
> "Delegate coding work to Codex, Claude Code, or OpenCode as background workers; not simple edits or read-only code lookup."

它正是靠这条 `description` 让 Agent1 在遇到「构建功能 / 大重构 / issue-to-PR」时自动想起「该委派给后台编码 worker」。PatchRelay 要解决的是同一类问题，因此**应当复用同一套 skill 机制**，而不是另起炉灶。

## 3. 推荐方案

**主方案：为 PatchRelay 编写一个 OpenClaw Skill（对标官方 `coding-agent`）。**
**辅助方案：同步收紧插件里三个工具的 `description`。**
**兜底（可选，非必需）：在 workspace `USER.md` 里加一行策略提示。**

### 为什么是 Skill 而不是塞系统提示

1. **渐进式披露**：只有一行 `description` 常驻，正文（如何提交、如何轮询、如何选 worker）只在相关时才加载，几乎不占用日常上下文预算。
2. **原生一致**：和官方 `coding-agent` 行为模型一致，Agent1 的选择行为可预测。
3. **可门控**：skill 的 `requires` 能绑定「二进制存在 + `skills.entries.patchrelay.enabled` + Server 可达」，PatchRelay 没启动时不会去骚扰用户，避免误触发。
4. **随仓库版本化**：SKILL.md 放进 `plugins/openclaw/`，和插件一起演进、一起分发，不污染用户全局系统提示。

### 3.1 新增 Skill 文件

新增 `plugins/openclaw/skills/patchrelay/SKILL.md`：

```markdown
---
name: patchrelay
description: "Delegate coding tasks (features, refactors, bug fixes, test writing) to a local PatchRelay worker via patchrelay_submit_task; not for read-only lookup or trivial one-line edits."
metadata:
  {
    "openclaw":
      {
        "emoji": "🛰️",
        "requires":
          {
            "config": ["skills.entries.patchrelay.enabled", "plugins.entries.patchrelay.enabled"]
          }
      }
  }
---

# PatchRelay

Use PatchRelay to hand off any non-trivial coding work to an isolated local
worker (Claude Code / Codex). PatchRelay runs the task in a dedicated Git
worktree, runs the configured tests, and returns status + diff + logs +
artifacts.

## When to use

Use it for: implementing a feature, multi-file refactor, bug fix, writing or
fixing tests, "make change X across the repo".

Do NOT use it for: read-only questions about the code, explaining code, or a
single trivial edit you can answer inline.

## Tools

- `patchrelay_submit_task` — submit the work. Returns a `taskId`.
- `patchrelay_get_task` — poll status / read diff, logs, test output, artifacts.
- `patchrelay_cancel_task` — cancel a queued or running task.

## Standard loop

1. Call `patchrelay_submit_task` with a clear, self-contained `instruction`.
   - `worker`: leave `auto` unless the user names one (`claude` / `codex`).
   - `testProfile`: `default` unless the user specifies another.
2. Take the returned `taskId`.
3. Poll with `patchrelay_get_task` until `status` is terminal
   (`completed` / `failed` / `cancelled`).
4. Report back to the user: summary, changed files, test result, and where the
   diff/artifacts are. On failure, surface the worker log tail; offer to
   resubmit with a refined instruction.

## Rules

- Write the `instruction` so the worker needs no follow-up: goal, target files
  or area, acceptance/test expectation.
- One task at a time (MVP runs serially); don't fan out.
- Never hand-edit the repo yourself as a silent substitute when PatchRelay is
  the intended path — if it fails, report and ask.
```

> 说明：`description` 是决定 Agent1 是否「想起」PatchRelay 的唯一常驻信号，务必写清**适用/不适用边界**（对标 `coding-agent` 的写法），避免它把「解释代码」这类只读请求也误派出去。

### 3.2 安装 / 启用 Skill

Skill 支持从本地目录安装。两种范围任选：

```powershell
# 安装到共享托管目录（对所有 agent 可见）
openclaw skills install C:\Users\57826\IdeaProjects\PatchRelayNEW\plugins\openclaw\skills\patchrelay --global

# 或安装到当前 agent 的 workspace
openclaw skills install C:\Users\57826\IdeaProjects\PatchRelayNEW\plugins\openclaw\skills\patchrelay
```

然后在 `C:\Users\57826\.openclaw\openclaw.json` 里启用（与现有 `plugins.entries.patchrelay` 并列，新增 `skills.entries`）：

```jsonc
"skills": {
  "entries": {
    "patchrelay": { "enabled": true }
  }
}
```

也可用 stdin patch，与项目现有 `openclaw config patch --stdin` 风格保持一致。

建议把这两步纳入 PatchRelay 自己的安装流程 —— 即在 `onboarding.py` 的
`build_openclaw_apply_steps()` 里，紧跟现有「install plugin / configure plugin」
之后追加「install skill / enable skill」两步，让 `patchrelay openclaw apply`
一键完成，避免又出现「插件装了但没人告诉 Agent1」的断层。

### 3.3 辅助：收紧工具 `description`

`plugins/openclaw/src/index.ts` 里当前描述过于简略。Skill 命中后，工具描述是 Agent1 决定「怎么调、传什么参数」的依据，建议改成自解释：

- `patchrelay_submit_task`:
  `"Delegate a coding task to a local PatchRelay worker (isolated Git worktree + tests). Returns a taskId to poll with patchrelay_get_task. Use for features, refactors, bug fixes, test writing — not read-only lookup."`
- `patchrelay_get_task`:
  `"Poll a PatchRelay task by taskId: status, phase, branch, worktree, diff, worker logs, test output, artifacts. Call repeatedly until status is completed/failed/cancelled."`
- `patchrelay_cancel_task`:
  保持现状即可，语义已清晰。

这属于「一次性、低风险」的文案增强，和 skill 是互补关系：skill 负责**何时用**，工具描述负责**怎么用**。

### 3.4 兜底（仅当 skill 描述仍不够时再加）

如果实测发现某些模型（如 DeepSeek）对 skill 描述的响应不够积极，再在 workspace
的 `USER.md` 里加**一行**策略提示：

```
Coding tasks (features, refactors, bug fixes) should be delegated via the PatchRelay skill, not hand-coded in this chat.
```

这是常驻上下文，属于最后手段，能不加就不加，避免 token 膨胀。

## 4. 验证方式

```powershell
# 1. skill 是否被模型可见
openclaw skills info patchrelay          # 期望 Visible to model: yes
openclaw skills check                    # 期望 patchrelay 在 Visible to model 计数内

# 2. 端到端：不带任何「用 PatchRelay」的提示，直接给 Agent1 一个编码任务
#    例如在 Dashboard 里说：「给 README 加一节 Troubleshooting」
#    期望：Agent1 自行调用 patchrelay_submit_task，而不是自己写。

# 3. 反向验证：给一个只读问题（「解释一下 NettySocketServer 怎么处理粘包」）
#    期望：Agent1 直接回答，不误派给 PatchRelay。
```

## 5. 结论

- **用 Skill，不用 hooks，也不要靠堆系统提示。** Skill 是 OpenClaw 为「能力发现 + 委派时机」原生设计的机制，官方 `coding-agent` 已验证同类场景。
- 主改动：新增 `plugins/openclaw/skills/patchrelay/SKILL.md` 并在配置里 `skills.entries.patchrelay.enabled: true`。
- 配套改动：收紧 `index.ts` 三个工具的 `description`；把「装 skill + 启用 skill」补进 `patchrelay openclaw apply` 流程。
- 可选兜底：`USER.md` 一行策略提示，仅在模型不够敏感时启用。
