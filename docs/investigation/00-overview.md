# PatchRelay × DeepSeek 问题排查总览

## 起点：用户反馈

OpenClaw Dashboard 中的 Agent1（DeepSeek V4 Flash）在会话里声称：

> "patchrelay_submit_task、patchrelay_get_task、patchrelay_cancel_task
> 这三个函数没有出现在我的调用列表里"

Agent1 随即绕行，改用 HTTP API 直接调用 PatchRelay Server。

---

## 问题全貌

```
OpenClaw Gateway（Agent1 / DeepSeek V4 Flash）
        ↓ 应该通过工具调用委派
PatchRelay Server（http://127.0.0.1:8787）
        ↓ 启动 worker
Claude Code / Codex（Agent2）
```

PatchRelay 通过 OpenClaw 插件注册了三个工具函数。Agent1 报告感知不到它们，
但实际的 HTTP API 调用是通的。

---

## 发现过程

### 第一阶段：验证配置层（怀疑：插件/工具未注入）

```bash
openclaw plugins inspect patchrelay --runtime --json
openclaw config get tools
openclaw skills info patchrelay
openclaw doctor
```

**结论：配置层完全正确。**
插件已加载（`status: loaded`），三个工具在 `toolNames` 里，skill 对模型可见，
doctor 无 patchrelay 相关警告。

---

### 第二阶段：嵌入式 agent 实测（怀疑：网关层过滤）

用嵌入式 agent 绕开网关，直接用真实配置测试：

```bash
openclaw agent --local --json --agent main \
  --session-key "agent:main:test" \
  --message "列出你以 patchrelay 开头的工具名"
```

DeepSeek 回答：

```
patchrelay_cancel_task, patchrelay_get_task, patchrelay_submit_task
```

追加测试：让它**调用**工具——模型发起了调用。

**结论：工具可用，嵌入式路径下模型能感知并调用。**

---

### 第三阶段：读会话快照（找最终证据）

读取 `~/.openclaw/agents/main/sessions/sessions.json`，
查看 `systemPromptReport.tools.entries`（OpenClaw 交给模型的工具 schema 记录）：

```
agent:main:main  →  total_tools=26
                    patchrelay=['patchrelay_submit_task',
                                'patchrelay_get_task',
                                'patchrelay_cancel_task']
```

**终极结论：OpenClaw 把三个工具写进了模型的 schema，工具从未缺失。**

---

## 真相

Agent1 的"我没有这些工具"是**模型的错误自我报告**，而非工具真的缺失。

这一发现引出了三个值得深究的问题：

| # | 问题 | 详见 |
|---|------|------|
| 1 | 为什么工具注入了，模型却说没有？（PatchRelay 具体根因） | `01-patchrelay-root-cause.md` |
| 2 | 模型回答问题时，到底走哪些路径？ | `02-model-output-paths.md` |
| 3 | 模型幻觉从何而来，如何系统性解决？ | `03-hallucination-solutions.md` |

---

## 顺带修复

排查过程中发现 `start.ps1` 将网关硬编码在 19001 端口，而 Dashboard 连接的是
配置文件声明的 18789 端口（由 schtasks 服务管理），造成端点分裂。已修复：
`start.ps1` / `stop.ps1` 现在从 `openclaw.json` 读取端口和 token，
`start.ps1` 优先用 `openclaw gateway restart` 重载服务网关。
