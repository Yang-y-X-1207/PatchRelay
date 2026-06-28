# PatchRelay 快速使用指南

## 🚀 一键启动

在 PowerShell 中运行：

```powershell
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay-tui\server
.\start.ps1
```

这个命令会依次打开：
1. **OpenClaw Gateway** 窗口（端口 19001）
2. **PatchRelay Server** 窗口（端口 8787）
3. **PatchRelay TUI** 监控界面
4. **OpenClaw Dashboard**（浏览器）

## 📋 启动后等待时间

- Gateway 启动：约 **5-10 秒**
- Server 启动：约 **10 秒**
- TUI 启动：约 **15 秒**
- **总计约 30 秒**所有服务完全就绪

## 🎯 使用流程

1. **运行启动脚本**
   ```powershell
   .\start.ps1
   ```

2. **等待所有窗口打开**（约 30 秒）
   - 确认每个窗口都显示 "ready" 或类似就绪状态

3. **在 OpenClaw Dashboard 中对话**
   - 浏览器会自动打开
   - 直接与 AI 对话，例如：
     ```
     "请帮我在 README.md 中添加一个使用示例"
     "修复登录页面的 CSS 样式问题"
     "重构 utils.js 中的日期处理函数"
     ```

4. **AI 自动调用 PatchRelay**
   - AI 会识别编码任务
   - 自动使用 `patchrelay_submit_task` 工具
   - Claude Code 在后台执行任务

5. **在 TUI 窗口监控进度**
   - 实时查看任务状态
   - 查看执行日志
   - 查看 diff 和变更

## 🛑 停止服务

```powershell
.\stop.ps1
```

或直接关闭所有 PowerShell 窗口。

## ⚠️ 常见问题

### 问题 1：端口被占用

**错误信息**：`[winerror 10048] 通常每个套接字地址(协议/网络地址/端口)只允许使用一次`

**解决方法**：
```powershell
# 1. 停止所有服务
.\stop.ps1

# 2. 如果还不行，强制停止
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process node -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*openclaw*" } | Stop-Process -Force

# 3. 重新启动
.\start.ps1
```

### 问题 2：某个窗口启动失败

**解决方法**：
1. 关闭所有窗口
2. 运行 `.\stop.ps1`
3. 等待 5 秒
4. 重新运行 `.\start.ps1`

### 问题 3：Dashboard 没有打开

**手动打开**：
```powershell
openclaw dashboard
```

### 问题 4：需要输入 Token

**Token 位置**：
- 脚本运行时会显示 token
- 或查看配置文件：`.\patchrelay.yaml` 中的 `server.token`
- 默认 token：`UEbjEGJaLR_UwEeHXf4PGAoTyzLIDJttXD2Ma6kt6JU`

## 📁 文件说明

### 脚本文件（在 `server/` 目录）

- **`start.ps1`** - 一键启动所有服务
- **`stop.ps1`** - 一键停止所有服务
- **`patchrelay.yaml`** - PatchRelay 配置文件

### 配置文件

**OpenClaw 配置**：`~/.config/openclaw/config.json`
```json
{
  "plugins": {
    "entries": {
      "patchrelay": {
        "enabled": true,
        "config": {
          "baseUrl": "http://127.0.0.1:8787",
          "token": "UEbjEGJaLR_UwEeHXf4PGAoTyzLIDJttXD2Ma6kt6JU"
        }
      }
    }
  }
}
```

## 🔧 高级配置

### 修改目标代码仓库

编辑 `patchrelay.yaml`：
```yaml
repo:
  path: C:\path\to\your\project  # 改为你的项目路径
  base_branch: main              # 改为你的主分支
```

### 修改测试命令

编辑 `patchrelay.yaml`：
```yaml
tests:
  default:
    command:
    - pytest              # Python 项目
    # - npm test          # Node.js 项目
    # - mvn test          # Java 项目
```

### 修改超时时间

编辑 `patchrelay.yaml`：
```yaml
limits:
  task_timeout_seconds: 7200  # 2 小时
```

## 📊 工作原理

```
用户在 OpenClaw Dashboard 对话
    ↓
AI 识别编码任务，调用 patchrelay_submit_task
    ↓
PatchRelay 接收任务，创建隔离的 Git worktree
    ↓
Claude Code 在后台执行任务
    ↓
PatchRelay 收集结果（diff, 日志, 测试结果）
    ↓
返回结果给 OpenClaw，显示在对话中
    ↓
用户在 TUI 中可以实时监控整个过程
```

## 🎓 完整示例

```powershell
# 1. 启动环境
cd C:\Users\57826\IdeaProjects\PatchRelay\PatchRelay-tui\server
.\start.ps1

# 2. 等待 30 秒让所有服务就绪

# 3. 在 OpenClaw Dashboard 中对话
# "请帮我优化 src/utils.js 中的日期格式化函数"

# 4. 在 TUI 窗口中观察任务执行

# 5. 任务完成后，查看结果
# 可以在 OpenClaw Dashboard 中看到 AI 返回的代码变更和说明

# 6. 停止服务
.\stop.ps1
```

## 📝 注意事项

1. **首次使用**需要等待较长时间（约 30 秒）
2. **端口冲突**时先运行 `.\stop.ps1`
3. **Token** 在脚本运行时会显示，保存备用
4. **关闭窗口**就等于停止该服务
5. **TUI 界面**按 Ctrl+C 退出
6. **任务隔离**：每个任务在独立的 Git worktree 中执行，不影响主分支

## 🆘 获取帮助

- 查看服务状态：`uv run patchrelay runtime status --config .\patchrelay.yaml`
- 查看任务列表：`uv run patchrelay tasks --token <your-token>`
- 查看任务详情：`uv run patchrelay get <task-id> --token <your-token>`
- 清理旧任务：`uv run patchrelay cleanup --config .\patchrelay.yaml --force`

---

**享受使用 PatchRelay！** 🎉
