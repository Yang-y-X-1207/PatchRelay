# PatchRelay 架构演进路线图

**文档版本**: v1.1  
**创建日期**: 2026-06-22  
**更新日期**: 2026-06-28  
**维护者**: PatchRelay 架构组  
**状态**: ✅ **Phase 1 已完成** | Phase 2 规划中

---

## 📋 文档目的

本文档描述 PatchRelay 从**本地部署**到**云端 SaaS** 的演进路线，以及相应的技术架构变化。

**重要更新（2026-06-28）：Phase 1 MVP 已全部完成并通过生产级任务验证。**

---

## 🎯 产品演进愿景

### 阶段划分

```
Phase 1: 本地工具 (MVP) ✅ 已完成
  └─ 用户下载 PatchRelay 到本地机器
  └─ 单机运行，直接操作本地代码仓库
  └─ 支持串行任务执行（一次一个任务）
  └─ 目标：10-50 并发任务（Phase 2）

Phase 2: 云端 SaaS 📋 规划中
  └─ 用户无需本地部署，直接使用云服务
  └─ 多租户架构，支持团队协作
  └─ 支持 1000+ 并发任务
```

---

## 🏗️ Phase 1: 本地部署架构（✅ 已完成）

### 完成状态（2026-06-28）

**已实现的核心功能：**
- ✅ 完整的端到端集成链路
- ✅ 一键启动脚本（`start.ps1`）
- ✅ OpenClaw 插件集成
- ✅ Claude Code / Codex worker 适配
- ✅ Git worktree 隔离
- ✅ 实时 TUI 监控界面
- ✅ HTTP REST API
- ✅ CLI 工具集
- ✅ 测试运行器
- ✅ 生产级任务验证

### 架构图

```
┌─────────────────────────────────────────────┐
│ 用户本地机器                                  │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │ OpenClaw Gateway (可选)              │  │
│  │ - 聊天入口                            │  │
│  │ - 工具调用                            │  │
│  └────────────┬─────────────────────────┘  │
│               │                             │
│  ┌────────────▼─────────────────────────┐  │
│  │ PatchRelay Server (Python)          │  │
│  │ ┌────────────────────────────────┐  │  │
│  │ │ FastAPI HTTP Server            │  │  │
│  │ │ - Bearer Token 认证             │  │  │
│  │ │ - A2A API                      │  │  │
│  │ └────────────────────────────────┘  │  │
│  │ ┌────────────────────────────────┐  │  │
│  │ │ Serial Task Queue              │  │  │
│  │ │ - 串行执行                      │  │  │
│  │ │ - SQLite 持久化                 │  │  │
│  │ └────────────────────────────────┘  │  │
│  │ ┌────────────────────────────────┐  │  │
│  │ │ Worker Manager                 │  │  │
│  │ │ - Claude Code Adapter          │  │  │
│  │ │ - Codex Adapter                │  │  │
│  │ │ - Fake Worker                  │  │  │
│  │ └────────────────────────────────┘  │  │
│  │ ┌────────────────────────────────┐  │  │
│  │ │ Git Workspace Manager          │  │  │
│  │ │ - Branch 创建                   │  │  │
│  │ │ - Worktree 隔离                 │  │  │
│  │ │ - Diff 收集                     │  │  │
│  │ └────────────────────────────────┘  │  │
│  └──────────────────────────────────────┘  │
│               │                             │
│  ┌────────────▼─────────────────────────┐  │
│  │ 本地代码仓库 (.git/)                  │  │
│  │ - main 分支                           │  │
│  │ - patchrelay/* 任务分支               │  │
│  │ - .patchrelay/ 状态目录               │  │
│  └──────────────────────────────────────┘  │
│                                             │
└─────────────────────────────────────────────┘
```

### 核心特点

✅ **完全本地** - 所有代码、数据都在用户机器上  
✅ **零配置云端** - 无需注册账号、无需上传代码  
✅ **隐私安全** - 代码不离开本地网络  
✅ **快速启动** - 下载即用，无依赖云服务  

### 适用场景

- 个人开发者本地使用
- 企业内网部署
- 代码安全性要求高
- 不需要团队协作

### 限制

⚠️ **并发能力** - 单机串行队列，并发有限  
⚠️ **资源限制** - 受限于本地机器性能  
⚠️ **团队协作** - 难以多人共享任务队列  
⚠️ **高可用** - 单点故障，机器关机服务停止  

---

## 🚀 Phase 2: 云端 SaaS 架构（未来）

### 整体架构图

```
┌──────────────────────────────────────────────────────────┐
│ 云端 (Cloud)                                              │
│                                                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Gateway 层 (Java 微服务)                            │  │
│  │ ┌──────────────────────────────────────────────┐  │  │
│  │ │ Spring Cloud Gateway                         │  │  │
│  │ │ - 负载均衡 (Ribbon/LoadBalancer)              │  │  │
│  │ │ - 限流熔断 (Sentinel/Resilience4j)           │  │  │
│  │ │ - 认证授权 (JWT/OAuth2)                      │  │  │
│  │ │ - API 路由                                    │  │  │
│  │ └──────────────────────────────────────────────┘  │  │
│  │ ┌──────────────────────────────────────────────┐  │  │
│  │ │ 多租户管理服务 (Java)                         │  │  │
│  │ │ - 用户注册/登录                               │  │  │
│  │ │ - 团队管理                                    │  │  │
│  │ │ - 配额管理                                    │  │  │
│  │ └──────────────────────────────────────────────┘  │  │
│  └────────────┬───────────────────────────────────────┘  │
│               │                                           │
│  ┌────────────▼───────────────────────────────────────┐  │
│  │ PatchRelay Pool (Python)                          │  │
│  │ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │  │
│  │ │ PatchRelay 1 │ │ PatchRelay 2 │ │ PatchRelay N│ │  │
│  │ │ (容器)        │ │ (容器)        │ │ (容器)      │ │  │
│  │ └──────────────┘ └──────────────┘ └────────────┘ │  │
│  │ - 动态扩缩容 (Kubernetes HPA)                      │  │
│  │ - 任务分发 (Redis Queue)                           │  │
│  │ - 状态同步 (PostgreSQL)                            │  │
│  └────────────┬───────────────────────────────────────┘  │
│               │                                           │
│  ┌────────────▼───────────────────────────────────────┐  │
│  │ 代码仓库存储                                        │  │
│  │ ┌──────────────────────────────────────────────┐  │  │
│  │ │ 方案 A: Git Server (GitLab/Gitea)            │  │  │
│  │ │ - 用户推送代码到云端 Git                      │  │  │
│  │ │ - PatchRelay 从云端 Git 拉取                  │  │  │
│  │ └──────────────────────────────────────────────┘  │  │
│  │ ┌──────────────────────────────────────────────┐  │  │
│  │ │ 方案 B: S3/OSS 对象存储                       │  │  │
│  │ │ - 用户上传代码快照                            │  │  │
│  │ │ - PatchRelay 下载并执行                       │  │  │
│  │ └──────────────────────────────────────────────┘  │  │
│  │ ┌──────────────────────────────────────────────┐  │  │
│  │ │ 方案 C: 反向代理到用户本地 (推荐)              │  │  │
│  │ │ - 用户本地运行 Agent                          │  │  │
│  │ │ - 云端通过 WebSocket 隧道调用本地 Git         │  │  │
│  │ └──────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
│                                                           │
└──────────────────────────────────────────────────────────┘
                           │
                           │ HTTPS API
                           │
                    ┌──────▼──────┐
                    │ 用户客户端   │
                    │ - Web UI    │
                    │ - CLI       │
                    │ - IDE 插件  │
                    └─────────────┘
```

### Gateway 层详细设计（Java）

#### 职责

1. **高并发处理**
   ```java
   // Spring WebFlux 异步非阻塞
   @RestController
   public class TaskGatewayController {
       @PostMapping("/api/v1/tasks")
       public Mono<TaskResponse> submitTask(@RequestBody TaskRequest request) {
           return rateLimiter.limit(request.getUserId())
               .flatMap(allowed -> taskService.submit(request))
               .timeout(Duration.ofSeconds(30));
       }
   }
   ```

2. **限流熔断**
   ```java
   // Sentinel 限流
   @SentinelResource(value = "submitTask", 
       blockHandler = "handleBlock",
       fallback = "handleFallback")
   public Mono<TaskResponse> submitTask(TaskRequest request) {
       // 每用户 10 QPS
       // 每租户 100 QPS
   }
   ```

3. **认证授权**
   ```java
   // JWT Token 验证
   @Component
   public class JwtAuthFilter implements WebFilter {
       public Mono<Void> filter(ServerWebExchange exchange, 
                                WebFilterChain chain) {
           String token = extractToken(exchange);
           return validateToken(token)
               .flatMap(claims -> {
                   exchange.getAttributes().put("userId", claims.getUserId());
                   return chain.filter(exchange);
               });
       }
   }
   ```

4. **路由转发**
   ```java
   // 动态路由到 PatchRelay 实例
   @Component
   public class PatchRelayRouter {
       public Mono<String> selectInstance(String tenantId) {
           // 根据租户 ID 哈希到固定实例（会话亲和性）
           // 或根据负载均衡算法选择
           return loadBalancer.choose(tenantId);
       }
   }
   ```

#### 技术栈

```xml
<!-- Spring Boot 3.x -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>

<!-- Spring Cloud Gateway -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway</artifactId>
</dependency>

<!-- Sentinel 限流 -->
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>spring-cloud-starter-alibaba-sentinel</artifactId>
</dependency>

<!-- Redis -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
</dependency>
```

### PatchRelay Pool 层（Python）

#### 改造要点

1. **状态外部化**
   ```python
   # 从 SQLite 迁移到 PostgreSQL
   DATABASE_URL = "postgresql://user:pass@postgres:5432/patchrelay"
   
   # 任务队列从内存迁移到 Redis
   QUEUE_URL = "redis://redis:6379/0"
   ```

2. **无状态化**
   ```python
   # 移除本地文件依赖
   # 从对象存储或 Git Server 获取代码
   async def fetch_code(repo_url: str, commit_sha: str) -> Path:
       # 下载代码到临时目录
       tmp_dir = Path(f"/tmp/repos/{commit_sha}")
       await git_clone(repo_url, tmp_dir, commit_sha)
       return tmp_dir
   ```

3. **容器化**
   ```dockerfile
   # Dockerfile
   FROM python:3.10-slim
   
   # 安装 Git、Claude CLI、Codex CLI
   RUN apt-get update && apt-get install -y git
   
   WORKDIR /app
   COPY PatchRelay .
   RUN pip install -e .
   
   CMD ["patchrelay", "serve", "--config", "/config/patchrelay.yaml"]
   ```

4. **水平扩展**
   ```yaml
   # Kubernetes HPA
   apiVersion: autoscaling/v2
   kind: HorizontalPodAutoscaler
   metadata:
     name: patchrelay
   spec:
     scaleTargetRef:
       apiVersion: apps/v1
       kind: Deployment
       name: patchrelay
     minReplicas: 3
     maxReplicas: 50
     metrics:
     - type: Resource
       resource:
         name: cpu
         target:
           type: Utilization
           averageUtilization: 70
   ```

### 代码仓库方案对比

#### 方案 A: 云端 Git Server

```
用户 → Push 代码到云端 Git → PatchRelay 从云端 Git Clone
```

**优点**:
- ✅ 完全云端化，无需本地 Agent
- ✅ 代码版本控制清晰

**缺点**:
- ❌ 用户需要上传代码（安全顾虑）
- ❌ 大仓库上传慢
- ❌ 存储成本高

#### 方案 B: 对象存储 (S3/OSS)

```
用户 → 上传代码快照到 S3 → PatchRelay 从 S3 下载
```

**优点**:
- ✅ 存储成本低
- ✅ 上传下载快

**缺点**:
- ❌ 用户需要上传代码（安全顾虑）
- ❌ 丢失 Git 历史

#### 方案 C: 反向代理隧道 (推荐) ⭐

```
用户本地运行 Agent → WebSocket 隧道 → 云端 PatchRelay → 通过隧道访问本地 Git
```

**架构**:
```
┌──────────────────┐         WebSocket          ┌─────────────┐
│ 用户本地机器      │ <─────────────────────────> │ 云端        │
│                  │                             │             │
│ ┌──────────────┐ │                             │ ┌─────────┐ │
│ │ Local Agent  │ │ ← 1. 建立长连接             │ │ Gateway │ │
│ │ (Python)     │ │                             │ └────┬────┘ │
│ └──────┬───────┘ │                             │      │      │
│        │         │                             │ ┌────▼────┐ │
│ ┌──────▼───────┐ │ ← 2. 接收 Git 命令           │ │PatchRelay│
│ │ 本地 Git 仓库 │ │                             │ │ Pool    │ │
│ └──────────────┘ │ → 3. 返回 Git 数据          │ └─────────┘ │
└──────────────────┘                             └─────────────┘
```

**实现**:
```python
# Local Agent
import asyncio
import websockets

async def local_agent():
    uri = "wss://api.patchrelay.com/agent?token=xxx"
    async with websockets.connect(uri) as ws:
        while True:
            # 接收来自云端的 Git 命令
            command = await ws.recv()
            cmd_type = command["type"]  # "git_clone", "git_diff"
            
            if cmd_type == "git_clone":
                # 执行本地 Git 命令
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", ...],
                    capture_output=True
                )
                # 返回结果
                await ws.send(json.dumps({
                    "stdout": result.stdout.decode(),
                    "stderr": result.stderr.decode(),
                    "exit_code": result.returncode
                }))
```

**优点**:
- ✅ 代码不离开本地（安全）
- ✅ 无需上传大文件（快）
- ✅ 保留 Git 完整功能
- ✅ 用户体验好（透明代理）

**缺点**:
- ⚠️ 需要用户本地运行 Agent
- ⚠️ 网络连接依赖（断线需重连）

**安全措施**:
- 双向 TLS 认证
- Token 授权
- 命令白名单（只允许安全的 Git 命令）
- 流量加密

---

## 🔄 技术栈对比

### 本地部署 vs 云端部署

| 组件 | 本地部署 (Phase 1) | 云端部署 (Phase 2) |
|-----|-------------------|-------------------|
| **API Gateway** | FastAPI (Python) | Spring Cloud Gateway (Java) |
| **认证** | Bearer Token | JWT + OAuth2 |
| **限流** | 无 | Sentinel + Redis |
| **负载均衡** | 无 | Ribbon / Spring Cloud LoadBalancer |
| **任务队列** | 内存队列 | Redis Queue |
| **数据库** | SQLite | PostgreSQL + Redis |
| **代码仓库** | 本地文件系统 | WebSocket 隧道 + Local Agent |
| **部署** | 单机进程 | Kubernetes + Docker |
| **监控** | 无 | Prometheus + Grafana |
| **日志** | 本地文件 | ELK / Loki |
| **扩展性** | 单机串行 | 水平扩展（1-N 实例）|

---

## 📈 性能和成本预估

### 本地部署（Phase 1）

```
硬件要求：
- CPU: 2 核
- 内存: 4 GB
- 磁盘: 20 GB

性能：
- 并发任务: 1（串行）
- TPS: 10-50
- 用户数: 1

成本：
- 零（用户自己的机器）
```

### 云端部署（Phase 2）

```
基础设施（AWS 估算）:

Gateway 层（Java）:
- ECS Fargate: 2 vCPU, 4 GB × 3 实例
- 成本: $150/月

PatchRelay Pool（Python）:
- ECS Fargate: 2 vCPU, 4 GB × 10 实例
- 成本: $500/月

数据库:
- RDS PostgreSQL: db.t3.medium
- 成本: $100/月

Redis:
- ElastiCache: cache.t3.micro
- 成本: $15/月

负载均衡:
- ALB: 2 个
- 成本: $50/月

对象存储（可选）:
- S3: 100 GB
- 成本: $3/月

总成本: ~$820/月（支持 500-1000 并发用户）

性能：
- 并发任务: 100+
- TPS: 500-1000
- 用户数: 1000+
```

---

## 🗺️ 迁移路线图

### Timeline

```
Q1 2026: Phase 1 - 本地部署 MVP ✅
├─ Week 1-4:   核心功能开发
├─ Week 5-6:   测试和文档
└─ Week 7-8:   发布 v0.1.0

Q2 2026: Phase 1 优化
├─ Week 1-4:   TUI 交互式 CLI
├─ Week 5-8:   性能优化、Bug 修复
└─ Week 9-12:  收集用户反馈

Q3 2026: Phase 2 准备
├─ Week 1-4:   Java Gateway POC
├─ Week 5-8:   Python 容器化改造
├─ Week 9-10:  Local Agent 开发
└─ Week 11-12: 集成测试

Q4 2026: Phase 2 Beta
├─ Week 1-4:   云端部署（内测）
├─ Week 5-8:   灰度发布（10% 用户）
├─ Week 9-10:  全量发布
└─ Week 11-12: 监控优化

Q1 2027: Phase 2 GA
├─ 稳定运营
├─ 企业版功能
└─ 国际化
```

### 关键里程碑

| 里程碑 | 时间 | 验收标准 |
|--------|------|---------|
| 本地 MVP 发布 | 2026-02 | 支持本地任务执行 |
| TUI CLI 完成 | 2026-04 | 实时任务监控 |
| Java Gateway 完成 | 2026-08 | 支持 1000 QPS |
| 云端 Beta | 2026-10 | 10 个企业客户内测 |
| 云端 GA | 2027-01 | 支持 1000+ 用户 |

---

## 🎯 决策点

### 何时启动 Phase 2？

**必要条件**（全部满足）:
- ✅ 本地版有 100+ 活跃用户
- ✅ 用户反馈需要团队协作功能
- ✅ 用户愿意为云服务付费
- ✅ 有资金支持云端开发（6-12 个月）

**充分条件**（满足任一）:
- ✅ 获得风险投资
- ✅ 有企业客户预付费
- ✅ 开源社区贡献者加入

### Gateway 用 Java 还是 Go？

**Java 的优势**:
- ✅ Spring 生态成熟（Gateway、Security、Cloud）
- ✅ 企业级功能丰富
- ✅ 团队可能已有 Java 经验

**Go 的优势**:
- ✅ 部署更简单（单二进制）
- ✅ 资源占用更低（省钱）
- ✅ 性能更好（延迟更低）

**推荐**: 如果团队会 Go，用 Go；否则用 Java（生态更完善）

---

## 🔒 安全考虑

### 数据安全

**本地部署**:
- ✅ 代码不离开本地
- ✅ 用户完全控制数据
- ✅ 符合高安全要求

**云端部署**:
- ⚠️ 需要加密传输（TLS）
- ⚠️ 需要加密存储（如果存储代码）
- ⚠️ 需要访问控制（IAM）
- ✅ 推荐使用 Local Agent 方案（代码不上传）

### 合规性

- GDPR（欧盟）
- SOC 2（美国）
- 等保 2.0（中国）

---

## 📚 参考架构

### 类似产品

1. **GitHub Codespaces**
   - 云端开发环境
   - Local Agent 连接本地代码

2. **GitLab CI/CD**
   - 云端 CI Runner
   - 本地 Runner Agent

3. **Tailscale**
   - 云端控制平面
   - 本地 Agent 建立 P2P 隧道

### 技术参考

- [Spring Cloud Gateway 文档](https://spring.io/projects/spring-cloud-gateway)
- [Kubernetes HPA 最佳实践](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [WebSocket 隧道设计模式](https://www.cloudflare.com/learning/network-layer/what-is-tunneling/)

---

## ✅ 总结

### 核心策略

**"本地先行，云端扩展"**

1. **Phase 1（本地）**: 
   - 快速验证产品概念
   - 零运营成本
   - 积累用户反馈

2. **Phase 2（云端）**:
   - Java Gateway 处理高并发
   - Python Pool 保留现有逻辑
   - Local Agent 保护代码安全

### 关键决策

- ✅ **不重写 Python** - 保留为业务逻辑层
- ✅ **Java 做网关** - 专注高并发和防护
- ✅ **Local Agent** - 解决代码安全问题
- ✅ **渐进演进** - 分阶段降低风险

### 成功指标

**Phase 1**:
- 100+ 本地活跃用户
- 10+ 企业团队使用
- 社区反馈积极

**Phase 2**:
- 1000+ 云端用户
- 99.9% 可用性
- < 100ms P95 延迟

---

## 📞 维护说明

本文档应在以下情况更新：
- 架构设计发生重大变化
- 技术选型调整
- 时间线变更
- 新的性能数据

**文档所有者**: 架构组  
**审阅周期**: 季度  
**下次审阅**: 2026-09-22

---

*本文档是 PatchRelay 产品规划的一部分，与 prd.md 配套使用*
