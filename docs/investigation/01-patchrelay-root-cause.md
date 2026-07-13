# 问题一：PatchRelay 工具感知失败根因分析

## 现象

Agent1（DeepSeek V4 Flash）在 OpenClaw Dashboard 中回答：
"三个 patchrelay 工具没有出现在我的调用列表里"。

被明确指示"调用 patchrelay_submit_task"时，模型**可以正确执行**。
被问"你有哪些工具"时，模型**回答错误**。

---

## 证据：工具从未缺失

```
会话                      总工具数    patchrelay 工具
agent:main:main（Dashboard）  26      三个全在 ✅
agent:main:pr-tooltest         26      三个全在 ✅
```

数据来源：`~/.openclaw/agents/main/sessions/sessions.json`
→ `systemPromptReport.tools.entries`（OpenClaw 交给模型的实际 schema 记录）

---

## 两种独立的失败

这不是一个问题，而是两个叠加的问题，成因不同：

```
失败类型               表现                       成因
─────────────────────────────────────────────────────────────
工具内省失败          问"你有什么工具"→ 回答错误   Flash 模型元认知能力弱
主动选用失败          接到编码任务→ 不会主动想到用  预训练未见过 patchrelay
```

---

## 根因详解

### 根因一：工具内省失败（Flash 模型元认知弱）

OpenClaw 通过 API 的 `tools` 参数注入工具 schema，这是一个独立于对话文本的区域。

- **执行路径**（被要求调用工具时）：模型主动查询 schema 区，生成合法调用 → 成功
- **文本生成路径**（被问及自身状态时）：模型做普通文字回答，不系统遍历 schema 区 → 失败

Flash/lite 模型参数规模小，RLHF 对元认知任务的覆盖不足，在"描述自己有什么工具"
这类任务上容易给出训练记忆中的默认话术而非实际状态。

### 根因二：主动选用失败（预训练陌生度）

`patchrelay_submit_task` 是完全自定义的工具名，在模型预训练语料中不存在。
当用户描述编码任务但未指定用哪个工具时，模型倾向于选用熟悉的工具
（`web_search`、`read`、直接回答），而不会联想到 patchrelay。

---

## 关键区分

```
工具注入  ✅
  ↓
模型执行能力  ✅（被明确指示时可以调用）
  ↓
模型内省能力  ❌（主动报告时回答错）
模型选用意愿  ❌（接到任务时不会主动想到用）
```

两个失败都**不需要微调**来修复——它们都可以通过上下文指令解决。

---

## 解决方案

### 方案一：强化 SKILL.md（解决主动选用 + 抑制内省幻觉）

在 SKILL.md 的规则节加强制性语句：

```markdown
## Hard rules

- When delegating a coding task, you MUST call `patchrelay_submit_task` directly.
  Do NOT call HTTP endpoints manually.
  Do NOT claim you lack the tool — the tool IS available; call it.
- If PatchRelay seems unavailable, call the tool and report the error;
  do not silently fall back to inline editing.
```

作用：每次 skill 触发时，把"工具一定存在，直接调用"这条规则注入模型上下文，
覆盖其错误的默认倾向。

### 方案二：切换模型（解决主动选用）

将 `agents.defaults.model.primary` 从 `deepseek/deepseek-v4-flash`
改为 `deepseek/deepseek-v4-pro`（无需新增凭证）。

Pro 模型经过更多工具调用 RLHF 训练，遵循上下文指令的能力更强，
主动选用 skill 指定工具的概率显著更高。

### 方案三：改变提问方式（绕开内省路径）

```
❌ "你有没有 PatchRelay 工具？"   ← 触发内省路径，易幻觉
✅ "用 PatchRelay 提交这个任务：<具体描述>"  ← 触发执行路径，直接调用
```

---

## 核心结论

> **工具已注入，模型已收到。问题是模型的两条路径表现不一致。
> 解法是用上下文指令引导模型走正确的路径，而不是修改工具注入层或微调模型。**
