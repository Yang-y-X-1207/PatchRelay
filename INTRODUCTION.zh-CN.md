# PatchRelay —— 两个编码 Agent 之间的桥

语言：[English](INTRODUCTION.md) | 简体中文

## 一句话概括

**PatchRelay 让一个 AI 编码 Agent 把真正的编码工作安全地交给另一个 Agent，
全程在你自己的机器上。** 你选两个 Agent：一个是你对话的前端，另一个在隔离的
Git worktree 里做实现，然后交回一份经过 review、跑过测试的 diff。

## 为什么需要它

单个编码 Agent 得在一个上下文里干所有事：规划、改代码、跑测试、还要记住这一切。
上下文很快就挤爆了，而且它把"我喜欢对话的那个 Agent"和"最擅长埋头改代码的那个
Agent"绑死在了一起。

PatchRelay 把这两个角色拆开：

- **Agent1（前端）** —— 理解你的意图、做规划、做 review。因为它不负责改文件，
  上下文保持干净。
- **Agent2（执行端）** —— 接收一份自包含的任务简报，在隔离分支上改动，跑测试套件，
  返回 diff + 日志 + 结果。

改动**从不直接碰你的工作区**。每个任务都跑在自己的 `git worktree`、自己的分支上，
所以一次跑砸了，只是一个可以丢掉的分支，而不是把你的仓库搞乱。

## 心智模型：一座桥

```
        你
         │  对话 / 读结果
         ▼
   ┌───────────┐        任务简报          ┌───────────┐
   │  Agent1   │ ───────────────────────▶ │ PatchRelay│
   │  （前端） │ ◀─────────────────────── │  （桥）   │
   └───────────┘   状态 · diff · 测试     └─────┬─────┘
                                                │ 隔离执行
                                                ▼
                                          ┌───────────┐
                                          │  Agent2   │
                                          │ （执行端）│──▶ git worktree + 测试
                                          └───────────┘
```

PatchRelay 是中间那座桥。它不写代码、也不是 Agent —— 它负责把任务入队、隔离、
调起你选的 worker、跑你的测试、收集产物。

## 两种拓扑，四种组合

你把哪个 Agent 放在前面，决定了桥的行为。

### 转发 —— Agent1 = OpenClaw

你在 OpenClaw 面板里对话。当你要一个编码改动时，OpenClaw 把它转发一次给
Agent2，再把结果给你看。一跳，单向。

```
  OpenClaw 面板 ──▶ PatchRelay ──▶ Claude 或 Codex ──▶ worktree + 测试
    （你对话）                        （执行端）
```

- **OpenClaw → Claude**
- **OpenClaw → Codex**

### 乒乓 —— Agent1 = Claude 或 Codex

桌面上的 Claude/Codex 会话就是你的前端。你跟*它*对话。它把你的需求变成一份简报，
交给 Agent2，读回返回的 diff 和测试结果，做 review，然后——对于多步工作——发出
下一份简报。来来回回，一跳接一跳，Agent1 当规划者/review 者，Agent2 当实现者。

```
  你 ─▶ 桌面 Claude ─▶ PatchRelay ─▶ Codex ─▶ worktree + 测试
   ▲       （Agent1）                （Agent2）      │
   └──────── review ◀── diff · 测试 ◀────────────────┘
                   （下一步重复）
```

- **Claude → Codex**
- **Codex → Claude**

## 每个任务你会拿回什么

- **status** —— `completed`、`failed` 或 `timed_out`
- **diff** —— 确切的改动，永远会捕获（哪怕失败/超时）
- **测试结果** —— 你配置的测试 profile 的输出
- **日志 & 产物** —— worker 的输出和一份任务摘要
- **分支 / worktree** —— 改动所在的位置，与你的主工作区隔离

## 它（暂时）还不是什么

PatchRelay 是一个**本地、单节点的 MVP**。一次跑一个任务、针对一个仓库、不会自动
commit/push 或建 PR。没有云端中继，也没有分布式 worker 池。重点是一条扎实的本地
闭环：提交 → 隔离 → 执行 → 测试 → 检查。往哪走见
[ARCHITECTURE_ROADMAP.md](ARCHITECTURE_ROADMAP.md)。

## 从这里开始

- **一条命令跑起来：** [USAGE.zh-CN.md](USAGE.zh-CN.md) —— 按 Agent 组合分场景的快速上手。
- **完整参考：** [README.zh-CN.md](README.zh-CN.md) —— 安装、配置、API、命令。
