# PatchRelay 产品需求文档

## 1. 产品概述

PatchRelay 是一个面向 Agent 编码任务的本地远程执行中继。它运行在开发者的本地机器或内网机器上，以 A2A Coding Execution Agent 的形式接收外部任务，把任务转交给本地专业编码工具，例如 Codex 和 Claude Code，并把进度、日志、diff、测试结果和最终状态返回给调用方。

PatchRelay 不重建 IM 网关、不重建完整 Coding Agent、不直接承担聊天会话管理。OpenClaw 负责用户入口、聊天平台接入和会话编排；PatchRelay 负责工程执行侧的任务接收、执行隔离、worker 调度、Git 分支管理、测试结果采集和交付状态回传。

核心链路如下：

```text
IM / Chat User
        |
        v
OpenClaw Gateway
        |
        v
PatchRelay OpenClaw Tool Plugin
        |
        v
PatchRelay Local A2A Server
        |
        v
Serial Task Queue
        |
        v
Codex Adapter / Claude Code Adapter
        |
        v
Git branch + worktree + diff + test artifacts
```

## 2. 产品目标

PatchRelay MVP 的目标是让远程用户可以通过 OpenClaw 发起一个编码任务，由本地开发机上的 PatchRelay 安全、可控地执行，并把结果以结构化方式返回。

MVP 需要达成以下效果：

- OpenClaw 能通过 Tool Plugin 调用 PatchRelay，而不是依赖 OpenClaw 是否原生支持 A2A Client。
- PatchRelay 对外暴露标准 A2A Server 能力，保持协议中立，未来可被其他 A2A Client 调用。
- PatchRelay 一次只处理一个任务，其他任务排队，降低并发冲突和 Git 风险。
- 每个任务使用独立 Git 分支和 worktree 执行，不污染主工作区。
- PatchRelay 支持 Codex 和 Claude Code 两个 worker adapter，并允许任务指定 worker。
- 执行结束后返回 changed files、diff、测试结果、日志摘要和最终状态。
- MVP 默认不 commit、不 push、不创建 PR，避免高风险 Git 交付动作过早进入自动化。

长期目标是在 Python 基本链路稳定后，把 PatchRelay 演进为双层架构：Java 控制面微服务负责高并发、高可用、调度、认证和任务主状态；Python 执行端退化为专注 Agent 执行的 worker executor，继续负责 Git worktree、Codex/Claude 调用、测试和 artifact 生成。这个演进不属于 MVP 首批范围，但 MVP 的任务模型、事件模型和 API 设计必须为后续拆分保留兼容空间。

## 3. 非目标

PatchRelay MVP 不做以下事情：

- 不实现 IM 网关、聊天机器人、多渠道消息接入。
- 不替代 OpenClaw 的 Gateway、session、routing 或 channel 能力。
- 不重建 Codex 或 Claude Code 的 agent loop。
- 不支持多仓库并发管理。
- 不支持多个任务并行执行。
- 不默认执行远端传入的任意 shell 命令。
- 不自动 commit、push 或创建 PR。
- 不在首版实现 Web 控制台。
- 不在首版实现公网反向隧道。
- 不在首版引入 Java 控制面微服务或分布式 worker 池。

## 4. 用户与场景

### 4.1 目标用户

主要用户是需要通过远程消息入口驱动本地编码工具的开发者、技术负责人或小团队。他们希望在手机、聊天工具或 OpenClaw 会话中提交编码任务，由本地机器上的 Codex 或 Claude Code 完成实际代码修改。

### 4.2 典型场景

远程用户在 OpenClaw 支持的聊天入口中发送：

```text
帮我修复登录接口 500 的问题，并运行单元测试。
```

OpenClaw 识别到需要调用 PatchRelay 后，通过 PatchRelay Tool Plugin 提交任务。PatchRelay 在本地仓库中创建任务分支和 worktree，调用 Codex 或 Claude Code 执行任务，运行配置好的测试 profile，最后把 diff、测试结果和日志摘要返回给 OpenClaw。

## 5. 语言选型

### 5.1 PatchRelay Core

PatchRelay Core 使用 Python。

选择：

- Python 3.12 作为推荐版本。
- Python 3.10 作为最低兼容版本。

原因：

- 用户明确偏好 Python。
- A2A 官方生态提供 Python SDK，适合快速实现 A2A Server。
- Python 适合本地命令编排、日志处理、Git 操作封装和测试工具集成。
- PatchRelay MVP 是本地执行端，单任务串行处理，对极限吞吐要求不高。

约束：

- 命令执行必须使用 argv 形式，不使用 shell 字符串拼接。
- 路径处理必须使用 `pathlib`。
- Windows 是首个优先支持平台，代码实现需考虑 Windows 进程树、路径和换行差异。

### 5.2 OpenClaw Tool Plugin

OpenClaw 适配层使用 TypeScript ESM。

选择：

- TypeScript ESM。
- Node.js >= 22。

原因：

- OpenClaw Tool Plugin 官方形态使用 TypeScript/JavaScript 插件。
- 插件只负责把 OpenClaw tool call 映射为 PatchRelay HTTP/A2A 调用，不承担复杂执行逻辑。
- TypeScript 能明确描述工具参数 schema，减少 OpenClaw 调用时的参数歧义。

### 5.3 Java Control Service

Java Control Service 是后续高并发、高可用阶段引入的控制面微服务，不参与 MVP 首批实现。

选择：

- Java 21 作为推荐运行版本。
- Spring Boot 作为默认 Web 和服务治理框架候选。
- 保留 Quarkus 作为轻量化部署候选，但除非有明确启动速度或原生镜像需求，否则不作为首选。

原因：

- Java 更适合长期运行的高并发 API 服务、任务调度服务和多实例高可用部署。
- Java 生态在认证、限流、连接池、队列消费、监控、治理和企业部署方面更成熟。
- 用户熟悉 Java，后续长期维护控制面时开发效率更高。
- Python 已经适合 Agent 执行链路，不需要用 Java 重写 worker 执行细节。

约束：

- Java 服务只接管控制面，不直接执行 Codex/Claude，也不直接修改目标仓库。
- Python 执行端必须先把任务协议、事件协议、artifact 协议稳定下来，再被 Java 调度。
- 第一阶段 Java 与 Python 使用 HTTP+JSON 通信；只有在协议稳定且性能瓶颈明确后，才考虑 gRPC。
- Java 控制面必须保持对当前外部 API 的兼容，避免 OpenClaw 插件和已有客户端被迫重写。

## 6. 技术栈选型

### 6.1 Python 后端

PatchRelay Core 使用以下技术栈：

- `uv`：Python 项目依赖和虚拟环境管理。
- `pyproject.toml`：项目元数据和依赖声明。
- A2A Python SDK：实现 A2A Server、Agent Card、任务协议映射。
- FastAPI / Starlette：本地 HTTP 服务和 REST endpoint。
- Uvicorn：ASGI server。
- Pydantic v2：配置、请求、响应和 artifact 数据结构校验。
- SQLite：本地任务状态、队列、日志索引和 artifact 元数据持久化。
- pytest：单元测试和集成测试。
- pytest-asyncio：异步 API 和队列测试。
- httpx：API 测试和 OpenClaw plugin fake endpoint 测试。
- psutil：Windows 下终止 worker 进程树。

### 6.2 TypeScript 插件

OpenClaw Tool Plugin 使用以下技术栈：

- TypeScript ESM。
- OpenClaw plugin SDK / tool plugin API。
- Node.js fetch API 或轻量 HTTP client。
- Zod 或 OpenClaw 推荐的 schema 定义方式，用于工具参数校验。

### 6.3 Git 与本地工具

PatchRelay 依赖以下本地工具：

- Git。
- Codex CLI。
- Claude Code CLI。
- 项目测试命令所需的语言运行时和包管理工具。

PatchRelay 不安装或管理 Codex、Claude Code、项目依赖，只在 `doctor` 检查中报告缺失项。

### 6.4 Java 控制面微服务

后续 Java Control Service 推荐使用以下技术栈：

- Java 21：长期支持版本，适合生产部署。
- Spring Boot：HTTP API、配置、健康检查、指标和服务集成。
- Spring Security：认证、授权和 API 访问控制。
- Micrometer / OpenTelemetry：指标、链路追踪和可观测性。
- PostgreSQL：生产级任务主状态、审计记录、用户和配置持久化。
- Redis 或兼容队列：任务排队、分布式锁、限流和短期状态缓存。
- Flyway 或 Liquibase：数据库 schema 迁移。
- Testcontainers：Java 集成测试中启动 PostgreSQL、Redis 和 Python executor fake service。

第一版 Java 服务不直接替换 Python server，而是作为控制面代理当前 Python API。等控制面稳定后，再把 Python 收缩为只提供内部 executor API 的执行服务。

## 7. 协议选型

### 7.1 外部协议

PatchRelay Core 对外采用 A2A latest HTTP+JSON/REST binding。

PatchRelay 作为 A2A Server，提供以下能力：

- Agent Card 能力发现。
- message send 任务提交。
- message stream 任务提交和流式更新。
- task get 任务查询。
- task list 任务列表。
- task cancel 任务取消。
- task subscribe 任务进度订阅。

### 7.2 OpenClaw 适配协议

OpenClaw 不被假设为原生 A2A Client。MVP 必须实现 PatchRelay OpenClaw Tool Plugin。

插件职责：

- 在 OpenClaw 中注册工具。
- 接收 OpenClaw 的工具调用参数。
- 调用 PatchRelay 本地 A2A/HTTP endpoint。
- 把 PatchRelay 的任务状态、日志摘要、diff 和测试结果转成 OpenClaw 可读文本或结构化结果。

插件不负责：

- 直接执行 Git 命令。
- 直接调用 Codex 或 Claude Code。
- 保存任务状态。
- 操作本地文件。

### 7.3 Worker 协议

PatchRelay 使用 adapter 模式封装 worker。

worker adapter 统一输入：

- 任务说明 instruction。
- worker 类型。
- worktree 路径。
- 任务上下文。
- 测试 profile。

worker adapter 统一输出：

- 结构化事件流。
- stdout/stderr 摘要。
- 退出码。
- 错误原因。
- 是否被取消。

Codex adapter 使用 Codex 非交互执行路径。Claude Code adapter 使用 Claude Code headless/print 模式和 stream-json 输出。

### 7.4 Java-Python 内部协议

Java 控制面引入后，外部客户端优先访问 Java API，Java 再通过内部协议调度一个或多个 Python executor。

内部协议第一阶段使用 HTTP+JSON：

```text
Java Control Service
  -> POST /internal/executions
  -> GET /internal/executions/{id}
  -> GET /internal/executions/{id}/events
  -> POST /internal/executions/{id}:cancel
  -> Python Executor Service
```

内部执行请求必须包含：

- `executionId`：由 Java 控制面生成的全局执行 id。
- `instruction`：用户任务说明。
- `repoId` 或 repo 配置快照。
- `baseBranch`。
- `worker`：`auto`、`codex`、`claude` 或后续扩展 worker。
- `testProfile`。
- `limits`：超时、日志大小、diff 大小等执行限制。
- `callback` 或事件拉取 cursor 配置。

内部执行响应必须包含：

- 当前状态和阶段。
- 事件序列号。
- worker 输出摘要。
- changed files。
- diff artifact 引用或内容。
- test artifact。
- error code 和 error message。

协议要求：

- `executionId` 必须幂等。Java 重试提交相同 `executionId` 时，Python 不能创建重复 worktree。
- 事件必须按 `sequence` 单调递增，便于 Java 聚合 SSE/WebSocket。
- cancel 必须是幂等操作。
- Python executor 不保存用户、租户、权限等控制面概念。
- Python executor 可以短期保存执行状态，但生产主状态以 Java 控制面的数据库为准。

## 8. 系统架构

### 8.1 模块划分

PatchRelay MVP 由以下模块组成：

- OpenClaw Tool Plugin：OpenClaw 侧薄适配器。
- A2A Server：对外任务协议入口。
- Auth Middleware：Bearer Token 认证。
- Config Loader：加载 `patchrelay.yaml`。
- Task Store：SQLite 持久化任务状态。
- Serial Queue：单任务串行执行。
- Git Workspace Manager：分支和 worktree 管理。
- Worker Manager：选择并运行 Codex 或 Claude Code adapter。
- Test Runner：执行配置好的测试 profile。
- Artifact Collector：收集 diff、changed files、日志、测试结果。
- Process Supervisor：管理 worker 进程和取消逻辑。
- CLI：本地管理和诊断工具。

### 8.2 数据流

任务提交数据流：

```text
OpenClaw tool call
  -> patchrelay_submit_task
  -> POST /message:send
  -> auth + request validation
  -> create task row
  -> enqueue task
  -> return task id
```

任务执行数据流：

```text
Serial queue
  -> create branch/worktree
  -> run selected worker
  -> stream logs/events
  -> run test profile
  -> collect git diff/artifacts
  -> mark completed/failed/canceled
```

结果查询数据流：

```text
OpenClaw tool call
  -> patchrelay_get_task
  -> GET /tasks/{id}
  -> return status + artifacts
  -> OpenClaw presents result to user
```

### 8.3 架构演进路线

PatchRelay 按三个阶段演进。

阶段一：Python 单体执行闭环。

```text
OpenClaw / API Client
        |
        v
Python PatchRelay Server
  - auth
  - task store
  - serial queue
  - Git worktree
  - Codex / Claude worker
  - tests
  - artifacts
        |
        v
Target Repository
```

目标是证明 Agent 编码任务的真实闭环：能接任务、能隔离执行、能运行 worker、能测试、能返回 diff 和事件。

阶段二：Java 控制面代理 Python 执行端。

```text
OpenClaw / API Client
        |
        v
Java Control Service
  - public API
  - auth
  - task master state
  - queue
  - rate limit
  - scheduler
        |
        v
Python PatchRelay Executor
  - Git worktree
  - Codex / Claude worker
  - tests
  - artifacts
```

目标是在不破坏 Python 执行能力的前提下，把高并发入口、主状态和调度能力迁到 Java。

阶段三：Python 退化为横向扩展 executor。

```text
OpenClaw / API Client
        |
        v
Java Control Service Cluster
        |
        v
Distributed Queue / Scheduler
        |
        +--> Python Executor Node A
        +--> Python Executor Node B
        +--> Python Executor Node C
```

目标是让 Python executor 成为可注册、可探活、可调度、可替换的执行节点；Java 控制面负责 worker 池、任务恢复、重试、审计和高可用。

### 8.4 Java 与 Python 职责边界

Java Control Service 负责：

- 对外统一 API。
- 用户、token、权限和租户边界。
- 任务主状态和审计记录。
- 队列、优先级、限流和重试。
- executor 注册、探活和调度。
- SSE/WebSocket 事件聚合。
- 高可用部署、监控、告警和运维入口。
- Git 交付审批流的主状态管理。

Python Executor 负责：

- 创建 Git branch 和 worktree。
- 调用 Codex / Claude / fake worker。
- 管理 worker 进程树、超时和取消。
- 运行 test profile。
- 收集 changed files、diff、worker 输出和测试结果。
- 生成 artifacts。
- 回传结构化事件 timeline。

明确不跨界：

- Java 不直接运行 Codex/Claude，不直接进入目标仓库修改文件。
- Python 不承担用户体系、租户体系、全局队列、生产审计和多实例调度。
- OpenClaw 插件不感知 Java/Python 内部分层，只调用稳定的 PatchRelay 外部 API。

## 9. 配置设计

PatchRelay 使用 `patchrelay.yaml` 作为本地配置文件。

配置项包括：

```yaml
server:
  host: 127.0.0.1
  port: 8787
  token: change-me

repo:
  path: C:\path\to\repo
  base_branch: main

worker:
  default: auto
  codex_command: codex
  claude_command: claude

tests:
  default:
    command: ["python", "-m", "pytest"]
  unit:
    command: ["python", "-m", "pytest", "tests"]
  lint:
    command: ["ruff", "check", "."]

limits:
  max_log_bytes: 1048576
  max_diff_bytes: 5242880
  task_timeout_seconds: 3600
```

配置规则：

- `repo.path` 必须是本地存在的 Git 仓库。
- `server.token` 不能为空，除非显式启用开发模式。
- `tests` 只能来自本地配置，远端请求只能选择 profile 名称。
- `worker.default` 支持 `auto`、`codex`、`claude`。
- `limits` 用于限制日志、diff 和任务最长执行时间。

## 10. 外部接口设计

### 10.1 Agent Card

接口：

```text
GET /.well-known/agent-card.json
```

功能：

- 返回 PatchRelay 的 A2A Agent Card。
- 声明 coding execution 能力。
- 声明支持 streaming。
- 声明 Bearer Token 认证要求。

验收标准：

- 未认证请求可以获取 Agent Card。
- Agent Card 中包含 PatchRelay 名称、版本、description、capabilities 和 endpoint。

### 10.2 提交任务

接口：

```text
POST /message:send
```

功能：

- 接收 A2A message。
- 从 message text 提取编码任务说明。
- 从 metadata 中读取 PatchRelay 扩展参数。
- 创建任务并加入串行队列。
- 返回 task id、初始状态和基础 metadata。

请求示例：

```json
{
  "message": {
    "role": "ROLE_USER",
    "parts": [
      {
        "text": "修复登录接口 500 的问题，并运行默认测试。"
      }
    ]
  },
  "metadata": {
    "patchrelay": {
      "worker": "auto",
      "baseRef": "main",
      "testProfile": "default"
    }
  }
}
```

验收标准：

- 没有 Bearer Token 的请求被拒绝。
- 空 instruction 被拒绝。
- 非法 worker 被拒绝。
- 非法 testProfile 被拒绝。
- 成功提交后任务状态为 `submitted` 或 `queued`。

### 10.3 流式提交

接口：

```text
POST /message:stream
```

功能：

- 提交任务。
- 通过 SSE 或 A2A 支持的 streaming 方式返回状态更新。
- 输出 Git 阶段、worker 阶段、测试阶段和 artifact 阶段的进度。

验收标准：

- 客户端能收到状态从 submitted 到 completed/failed/canceled 的变化。
- worker 输出被截断和脱敏后流式返回。
- 客户端断开不影响后台任务继续执行。

### 10.4 查询任务

接口：

```text
GET /tasks/{id}
GET /tasks
```

功能：

- 查询单个任务详情。
- 查询最近任务列表。
- 返回任务状态、worker、branch、changed files、测试状态、artifact 摘要。

验收标准：

- 不存在的 task id 返回明确错误。
- 已完成任务返回 diff、tests、summary、log artifact 引用或内容。
- 运行中任务返回当前阶段和日志摘要。

### 10.5 取消任务

接口：

```text
POST /tasks/{id}:cancel
```

功能：

- 取消 queued 或 working 任务。
- 对 working 任务终止 worker 进程树。
- 标记任务为 canceled。

验收标准：

- queued 任务取消后不会执行。
- working 任务取消后 Codex/Claude Code 子进程被终止。
- completed/failed 任务不能被取消，返回明确错误。

## 11. OpenClaw Tool Plugin 功能

### 11.1 兼容性 Spike

优先级：P0-1。

目标：

- 验证 OpenClaw Tool Plugin 能否注册工具。
- 验证 Gateway 能否发现插件工具。
- 验证插件能否调用本地 HTTP endpoint。
- 验证工具调用结果能否回到 OpenClaw 对话中。

实现内容：

- 创建最小 OpenClaw 插件项目。
- 注册一个 fake tool。
- fake tool 调用 `http://127.0.0.1:8787/health` 或 fake PatchRelay endpoint。
- 通过 OpenClaw 官方校验命令验证插件配置。

验收标准：

- OpenClaw 能显示 PatchRelay 相关工具。
- 工具调用能成功访问本地服务。
- OpenClaw 对话中能看到工具返回结果。

风险：

- 如果 OpenClaw 插件加载或工具调用机制与文档不一致，需要先调整适配方式。
- 如果 OpenClaw 不能从当前运行环境访问 `127.0.0.1`，需要改为内网地址或其他连接方式。

### 11.2 `patchrelay_submit_task`

优先级：P0-2。

功能：

- 接收 OpenClaw 发来的编码任务。
- 校验 instruction、worker、testProfile。
- 调用 PatchRelay `/message:send`。
- 返回 task id、状态、worker、branch 或排队信息。

参数：

- `instruction`：必填，用户编码任务说明。
- `worker`：可选，`auto`、`codex`、`claude`。
- `testProfile`：可选，必须匹配 PatchRelay 本地配置。

验收标准：

- 参数缺失时返回可读错误。
- PatchRelay 不可达时返回连接错误和诊断建议。
- 成功后 OpenClaw 能看到 task id 和下一步查询方式。

### 11.3 `patchrelay_get_task`

优先级：P0-2。

功能：

- 按 task id 查询任务状态。
- 返回当前阶段、日志摘要、changed files、diff 和测试结果。
- 对超长 diff 或日志进行摘要。

参数：

- `taskId`：必填。

验收标准：

- 运行中任务返回当前进度。
- 完成任务返回最终结果。
- 失败任务返回失败原因和关键日志。

### 11.4 `patchrelay_cancel_task`

优先级：P0-2。

功能：

- 按 task id 取消任务。
- 调用 PatchRelay cancel endpoint。
- 返回取消结果。

参数：

- `taskId`：必填。

验收标准：

- queued 任务可取消。
- working 任务可取消。
- 已结束任务返回不可取消原因。

## 12. PatchRelay A2A Server 功能

### 12.1 本地服务启动

优先级：P0-3。

功能：

- 启动 HTTP 服务。
- 读取配置文件。
- 初始化 SQLite。
- 初始化任务队列。
- 注册 A2A endpoints。

验收标准：

- `patchrelay serve` 能启动服务。
- 默认监听 `127.0.0.1:8787`。
- 配置错误时启动失败并输出明确原因。

### 12.2 Bearer Token 认证

优先级：P0-4。

功能：

- 除 Agent Card 和健康检查外，所有 API 必须认证。
- 支持从配置或环境变量读取 token。
- 认证失败返回 401。

验收标准：

- 无 token 请求被拒绝。
- 错误 token 请求被拒绝。
- 正确 token 请求通过。

### 12.3 健康检查

优先级：P0-4。

功能：

- 提供本地 health endpoint。
- 返回服务版本、配置仓库、队列状态、worker 可用性摘要。

验收标准：

- OpenClaw Spike 能通过 health endpoint 验证连接。
- 缺少 Codex 或 Claude Code 时 health 能报告 warning。

## 13. 任务状态机与队列

### 13.1 任务状态

优先级：P0-5。

状态包括：

- `submitted`：任务已接收。
- `queued`：任务等待执行。
- `working`：任务正在执行。
- `input-required`：任务等待用户审批或输入。
- `completed`：任务成功完成。
- `failed`：任务失败。
- `canceled`：任务被取消。

状态规则：

- submitted 可以进入 queued 或 working。
- queued 可以进入 working 或 canceled。
- working 可以进入 input-required、completed、failed 或 canceled。
- input-required 可以进入 working、failed 或 canceled。
- completed、failed、canceled 是终态。

验收标准：

- 状态转换被持久化。
- 非法状态转换被拒绝。
- 服务重启后能恢复任务记录。

### 13.2 串行队列

优先级：P0-5。

功能：

- 一次只运行一个任务。
- 后续任务排队。
- 任务完成后自动执行下一个任务。

验收标准：

- 同时提交两个任务时，只会有一个进入 working。
- 第一个任务结束后第二个任务开始。
- 取消 queued 任务后不会影响 running 任务。

## 14. Git 分支与 worktree 隔离

### 14.1 任务分支

优先级：P0-6。

功能：

- 每个任务创建独立 Git 分支。
- 分支命名格式为 `patchrelay/YYYYMMDD/<short-task-id>`。
- 默认基于配置的 `repo.base_branch` 创建。

验收标准：

- 分支名唯一。
- base branch 不存在时任务失败并返回明确错误。
- 分支创建失败时不会继续执行 worker。

### 14.2 Worktree

优先级：P0-6。

功能：

- 每个任务使用独立 Git worktree。
- worktree 位于 PatchRelay 状态目录下。
- worker 和测试命令都在 worktree 中执行。

验收标准：

- 主工作区不被直接修改。
- 任务完成后 worktree 保留，方便人工检查。
- 后续提供清理命令，但 MVP 不自动删除。

### 14.3 Git 结果采集

优先级：P0-9。

功能：

- 执行 `git status --porcelain` 获取变更文件。
- 执行 `git diff --binary` 获取完整 diff。
- 记录 branch、base branch、worktree path。

验收标准：

- 无变更任务返回 changed files 为空和空 diff。
- 有变更任务返回准确文件列表。
- diff 超过限制时返回截断提示。

## 15. Worker Adapter

### 15.1 统一 Worker 接口

优先级：P0-7。

功能：

- 为 Codex 和 Claude Code 定义统一 adapter 接口。
- 支持 start、stream events、cancel、collect result。
- 统一映射 stdout/stderr、退出码、错误原因。

验收标准：

- 上层任务执行器不需要关心具体 worker 类型。
- fake worker 可用于测试任务状态机。

### 15.2 Codex Adapter

优先级：P0-7。

功能：

- 在 worktree 中调用 Codex 非交互执行模式。
- 传入 instruction。
- 收集 JSON 或文本输出。
- 捕获退出码和异常。

验收标准：

- Codex 可用时能执行任务。
- Codex 不存在时返回明确错误。
- Codex 失败退出时任务标记为 failed。
- Codex 输出可被记录为日志 artifact。

### 15.3 Claude Code Adapter

优先级：P0-8。

功能：

- 在 worktree 中调用 Claude Code headless/print 模式。
- 使用 stream-json 输出时解析事件流。
- 捕获退出码和异常。

验收标准：

- Claude Code 可用时能执行任务。
- Claude Code 不存在时返回明确错误。
- Claude Code 失败退出时任务标记为 failed。
- stream-json 异常时任务不会崩溃，返回可诊断错误。

### 15.4 Worker 选择

优先级：P0-7。

功能：

- 请求可指定 `worker`。
- 支持 `auto`、`codex`、`claude`。
- `auto` 使用配置中的默认 worker 或可用 worker 优先级。

验收标准：

- 非法 worker 被拒绝。
- 指定 worker 不可用时任务失败并提示。
- `auto` 在至少一个 worker 可用时能选择执行器。

## 16. 测试 Profile

### 16.1 Profile 配置

优先级：P0-10。

功能：

- 用户在 `patchrelay.yaml` 中配置测试 profile。
- 任务只能通过 profile 名称选择测试命令。
- 不允许远端请求直接传 shell command。

验收标准：

- 合法 profile 可执行。
- 非法 profile 被拒绝。
- 未指定 profile 时使用 `default`。

### 16.2 测试执行

优先级：P0-10。

功能：

- 在任务 worktree 中执行测试命令。
- 采集 stdout、stderr、退出码、耗时。
- 将测试结果加入 artifact。

验收标准：

- 测试成功时 task summary 中 `testStatus=passed`。
- 测试失败时 task summary 中 `testStatus=failed`，任务是否 failed 由配置决定，MVP 默认 failed。
- 测试超时时终止进程并记录 timeout。

## 17. Artifacts

### 17.1 Summary Artifact

优先级：P0-9。

内容：

- task id。
- worker。
- branch。
- base branch。
- worktree path。
- changed files。
- test status。
- task status。
- duration。
- exit code。

验收标准：

- 每个终态任务都有 summary。
- summary 可被 OpenClaw 插件转成简洁文本。

### 17.2 Diff Artifact

优先级：P0-9。

内容：

- `git diff --binary` 输出。
- 文件数量。
- diff 是否被截断。

验收标准：

- diff 能用于人工审查。
- 超限 diff 返回截断标记和本地文件路径。

### 17.3 Test Artifact

优先级：P0-9。

内容：

- profile 名称。
- command argv。
- stdout 摘要。
- stderr 摘要。
- exit code。
- duration。

验收标准：

- 测试结果能被 OpenClaw 返回给用户。
- 敏感信息会被脱敏。

### 17.4 Log Artifact

优先级：P0-9。

内容：

- worker 输出。
- Git 阶段日志。
- 测试阶段日志。
- 错误堆栈摘要。

验收标准：

- 日志不超过配置限制。
- token、API key 等敏感信息被替换。

## 18. 取消与进程管理

### 18.1 取消 queued 任务

优先级：P0-11。

功能：

- 将 queued 任务标记为 canceled。
- 从队列中跳过该任务。

验收标准：

- canceled queued 任务不会启动 worker。

### 18.2 取消 working 任务

优先级：P0-11。

功能：

- 标记任务取消请求。
- 终止 worker 主进程和子进程。
- 终止测试进程。
- 保存取消日志。

验收标准：

- Windows 下不会遗留 Codex/Claude Code 子进程。
- 取消后任务进入 canceled 终态。

## 19. 安全策略

### 19.1 认证

优先级：P0-4。

功能：

- Bearer Token 保护 API。
- Token 支持配置文件和环境变量。
- 插件通过环境变量读取 token。

验收标准：

- token 不出现在日志中。
- 认证失败不会泄漏任务信息。

### 19.2 命令安全

优先级：P0-10。

功能：

- 远端只能选择 test profile。
- worker 命令来自本地配置。
- 命令执行使用 argv。

验收标准：

- 远端无法注入 shell 命令。
- 配置中的命令可以被完整审计。

### 19.3 日志脱敏

优先级：P1-4。

功能：

- 对常见 token、API key、Bearer header、环境变量密钥做 redaction。
- 限制日志和 diff 大小。

验收标准：

- 测试样例中的 secret 不会出现在 artifact 中。

## 20. 本地 CLI

### 20.1 `patchrelay serve`

优先级：P1-3。

功能：

- 启动本地 A2A Server。
- 支持指定配置文件。

验收标准：

- 服务启动后可访问 Agent Card 和 health endpoint。

### 20.2 `patchrelay tasks`

优先级：P1-3。

功能：

- 查看任务列表。
- 支持按状态过滤。

验收标准：

- 能显示最近任务 id、状态、worker、branch 和耗时。

### 20.3 `patchrelay cancel`

优先级：P1-3。

功能：

- 本地取消任务。

验收标准：

- 与 HTTP cancel 行为一致。

### 20.4 `patchrelay doctor`

优先级：P1-3。

功能：

- 检查配置文件。
- 检查 Git 仓库。
- 检查 Codex CLI。
- 检查 Claude Code CLI。
- 检查测试 profile。

验收标准：

- 输出可执行的诊断建议。

## 21. Windows 支持与打包

### 21.1 Windows 优先支持

优先级：P1-5。

功能：

- 支持 PowerShell 环境。
- 支持 Windows 路径。
- 支持 Windows 进程树取消。

验收标准：

- 在 Windows 上能完成端到端任务。

### 21.2 启动脚本

优先级：P1-5。

功能：

- 提供启动服务的脚本。
- 提供配置样例。
- 提供 doctor 检查。

验收标准：

- 用户可以按 README 步骤启动 PatchRelay。

## 22. 后续路线

### 22.1 多仓库支持

优先级：P2-1。

功能：

- 支持 repo registry。
- 任务可指定 `repoId`。
- 每个 repo 有独立 base branch、test profiles 和权限策略。

验收标准：

- 任务只能访问 allowlist 中的仓库。

### 22.2 反向隧道模式

优先级：P2-2。

功能：

- 本地 PatchRelay 主动连接远端 relay。
- 支持 OpenClaw Gateway 在云端、本地执行端在开发机的场景。

验收标准：

- 不需要公网暴露本地 PatchRelay 端口。
- 连接断开后能重连并恢复可见状态。

### 22.3 Commit / Push / PR

优先级：P2-3。

功能：

- 支持审批后本地 commit。
- 支持审批后 push。
- 支持创建 GitHub/GitLab PR。

验收标准：

- 所有高风险动作都需要 OpenClaw 对话审批。
- 审批记录可审计。
- push/PR 失败时返回明确错误。

### 22.4 Web 控制台

优先级：P2-4。

功能：

- 展示任务列表。
- 查看日志和 diff。
- 执行审批。
- 查看配置和 worker 健康状态。

验收标准：

- 不影响 A2A API 和 OpenClaw 插件主链路。

## 23. 实现优先级总表

| 顺序 | 优先级 | 功能 | 目标 |
| --- | --- | --- | --- |
| 1 | P0-1 | OpenClaw 兼容性 Spike | 验证 OpenClaw Tool Plugin 能调用本地 PatchRelay |
| 2 | P0-2 | OpenClaw Tool Plugin | 提供 submit/get/cancel 工具 |
| 3 | P0-3 | PatchRelay A2A Server | 提供本地 A2A/HTTP 任务入口 |
| 4 | P0-4 | 配置与认证 | 加载配置并保护 API |
| 5 | P0-5 | 任务状态机与串行队列 | 支持任务生命周期和单任务执行 |
| 6 | P0-6 | Git 分支与 worktree | 隔离每个任务的代码修改 |
| 7 | P0-7 | Codex Adapter | 支持 Codex 执行任务 |
| 8 | P0-8 | Claude Code Adapter | 支持 Claude Code 执行任务 |
| 9 | P0-9 | Artifacts | 返回 diff、日志、测试结果和 summary |
| 10 | P0-10 | 测试 Profile | 安全执行本地预定义测试 |
| 11 | P0-11 | 取消与进程树清理 | 取消任务并清理 worker 进程 |
| 12 | P1-1 | A2A Streaming | 实时回传任务进度 |
| 13 | P1-2 | OpenClaw 对话审批 | 为高风险动作预留审批流程 |
| 14 | P1-3 | 本地 CLI | 支持 serve/tasks/cancel/doctor |
| 15 | P1-4 | 安全与日志脱敏 | 限制泄密和 artifact 尺寸 |
| 16 | P1-5 | Windows 打包与启动脚本 | 降低本地部署成本 |
| 17 | P2-1 | 多仓库支持 | 支持 repo registry |
| 18 | P2-2 | 反向隧道模式 | 支持云端 OpenClaw 到本地 PatchRelay |
| 19 | P2-3 | Commit / Push / PR | 支持审批后的完整 Git 交付 |
| 20 | P2-4 | Web 控制台 | 提供可视化任务管理 |

## 24. 测试计划

### 24.1 OpenClaw 插件测试

- 插件 manifest 可被 OpenClaw 识别。
- 工具 schema 正确。
- `patchrelay_submit_task` 能调用 fake endpoint。
- `patchrelay_get_task` 能解析 fake task response。
- `patchrelay_cancel_task` 能处理成功和失败响应。

### 24.2 A2A API 测试

- Agent Card 返回正确。
- 未认证请求被拒绝。
- 合法任务可提交。
- 非法 metadata 被拒绝。
- task get/list/cancel 行为正确。
- streaming 能返回状态更新。

### 24.3 Git 集成测试

- 临时 repo 中能创建任务分支。
- worktree 创建成功。
- worker 修改文件后能收集 changed files。
- diff 内容正确。
- base branch 不存在时失败。

### 24.4 Worker Adapter 测试

- fake Codex 成功输出。
- fake Codex 失败退出。
- fake Claude Code stream-json 成功。
- fake Claude Code 输出异常 JSON。
- worker 超时。
- worker 取消。

### 24.5 端到端验收

端到端验收必须覆盖：

- OpenClaw 调用 `patchrelay_submit_task`。
- PatchRelay 创建任务。
- PatchRelay 创建 Git branch 和 worktree。
- worker 修改文件。
- PatchRelay 执行测试 profile。
- OpenClaw 调用 `patchrelay_get_task`。
- 用户看到 changed files、diff、测试结果和最终状态。

## 25. 验收标准

MVP 通过验收需要满足：

- OpenClaw 能发现 PatchRelay 插件工具。
- OpenClaw 能提交任务到本地 PatchRelay。
- PatchRelay 能串行执行任务。
- PatchRelay 能分别调用 Codex 和 Claude Code。
- PatchRelay 能在独立分支和 worktree 中完成修改。
- PatchRelay 能返回 diff、日志、测试结果和 summary。
- PatchRelay 默认不会 commit、push 或创建 PR。
- PatchRelay 能取消 queued 和 working 任务。
- PatchRelay 能在 Windows 环境完成主要链路。

## 26. 风险与应对

### 26.1 OpenClaw 适配风险

风险：

- OpenClaw 当前公开文档没有稳定声明原生 A2A Client 调用外部 A2A Agent 的能力。

应对：

- MVP 必须包含 OpenClaw Tool Plugin。
- 第一优先级做兼容性 Spike。

### 26.2 Worker CLI 兼容风险

风险：

- Codex 或 Claude Code CLI 参数、输出格式可能变化。

应对：

- adapter 隔离 worker 细节。
- 使用 fake worker 测试核心流程。
- `doctor` 检查 worker 版本和可用性。

### 26.3 Git 工作区风险

风险：

- 任务执行可能污染主工作区或覆盖用户改动。

应对：

- 使用独立 branch 和 worktree。
- 不在主工作区运行 worker。
- 默认不 push、不 reset 用户分支。

### 26.4 安全风险

风险：

- 远端任务可能诱导执行危险命令或泄露 secret。

应对：

- 远端不能传任意测试命令。
- API 使用 Bearer Token。
- 日志和 artifact 脱敏。
- 高风险 Git 动作放到后续版本并要求审批。

## 27. 参考资料

- [OpenClaw Tool plugins](https://docs.openclaw.ai/plugins/tool-plugins)
- [OpenClaw Building plugins](https://docs.openclaw.ai/plugins/building-plugins)
- [OpenClaw Plugin manifest](https://docs.openclaw.ai/plugins/manifest)
- [A2A Specification](https://a2a-protocol.org/latest/specification/)
- [A2A Python SDK](https://a2a-protocol.org/latest/tutorials/python/2-setup/)
- [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive)
- [Claude Code CLI reference](https://docs.anthropic.com/en/docs/claude-code/cli-usage)
