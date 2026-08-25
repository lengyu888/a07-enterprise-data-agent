# 阶段 0 测试报告

| 项目 | 结果 |
|---|---|
| 测试日期 | 2026-08-25 |
| Git 分支 | `phase/00-bootstrap` |
| Docker 构建 | 通过 |
| 三容器启动 | 通过 |
| PowerShell 冒烟测试 | 通过 |
| Playwright 桌面端 | 通过 |
| Playwright 移动端 | 通过 |
| 浏览器控制台错误 | 0 |
| npm audit | 0 个已知漏洞 |
| DeepSeek 实际请求 | 通过（Docker Secret，`deepseek-v4-pro`） |

## 1. 已验证内容

- `a07-agent-postgres-1`、`a07-agent-app-1`、`a07-agent-web-1` 均为 healthy；
- PostgreSQL 连接成功，`app.app_config` 初始化成功；
- `/api/health` 返回 `ok`；
- `/api/ready` 返回 `ready`，数据库依赖为 `ready`；
- `/api/v1/system/bootstrap` 返回 `phase-0`；
- Web 首页可访问并正确显示实时依赖状态；
- “重新检测”交互有效；
- 1440×1000 桌面视口和 390×844 移动视口均通过；
- 前端生产构建通过 TypeScript 检查与 Vite 构建；
- Vite 已升级到安全公告修复版本。
- `/api/v1/system/deepseek/probe` 返回 `ready`，DeepSeek 实际请求通过。

## 2. 用户测试入口

- 工作台：<http://localhost:8080>
- FastAPI 文档：<http://localhost:8000/docs>
- 后端存活：<http://localhost:8000/api/health>
- 后端就绪：<http://localhost:8000/api/ready>

本机测试命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-stage0.ps1
```

## 3. DeepSeek 安全配置

原宿主环境 Key 曾被 Compose 配置输出展开，应先在 DeepSeek 控制台轮换。新 Key 只写入 `.secrets/deepseek_api_key`，使用：

```powershell
docker compose -f compose.yml -f compose.deepseek.yml up --build -d
```

随后调用：

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/system/deepseek/probe
```

不得把 Secret 文件、Key、完整 Compose 配置或含鉴权头的请求日志提交到 Git。

## 4. 阶段确认门

请用户确认：

- [x] 工作台页面符合预期；
- [x] 三容器可在本机稳定启动；
- [x] API 文档可访问；
- [x] 冒烟脚本全部通过；
- [x] 已配置新的 DeepSeek Key（Docker Secret）；
- [x] 新 Key 的 probe 通过；
- [x] 同意提交阶段 0、创建 `phase-0` 标签并配置/推送 GitHub remote。

用户未确认前，不创建阶段提交，不推送远程仓库。
