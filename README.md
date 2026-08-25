# A07 企业数据底座智能问析 Agent

浙江省大学生服务外包创新应用大赛 A07 赛题的 12 周比赛版本实现。

核心技术主线：DeepSeek + LangGraph + 业务/Schema RAG + Text-to-SQL。

## 当前阶段

阶段 0：Git 与三容器工程骨架。

- Vue 3 Web 工作台；
- FastAPI 模块化单体；
- PostgreSQL 16 + pgvector；
- DeepSeek 服务端适配器骨架；
- Docker Compose 本地构建、健康检查与验收脚本。

业务 Agent、数据目录、RAG 和 Text-to-SQL 将按阶段计划逐步实现。

## 本地启动

1. 可选：复制环境变量模板。

   ```powershell
   Copy-Item .env.example .env
   ```

2. 构建并启动。

   ```powershell
   docker compose up --build -d
   ```

3. 查看容器状态。

   ```powershell
   docker compose ps
   ```

4. 打开工作台：<http://localhost:8080>

5. 执行阶段 0 冒烟测试。

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\test-stage0.ps1
   ```

6. 停止服务。

   ```powershell
   docker compose down
   ```

不要执行 `docker compose down -v`，除非确认要清空本地数据库卷。

## DeepSeek 配置

真实 API Key 不进入 Compose 环境变量，也不写入 `.env`。如需调用 DeepSeek，创建被 Git 忽略的 Secret 文件：

```powershell
New-Item -ItemType Directory -Force .secrets
Set-Content -NoNewline .secrets\deepseek_api_key 'your_key'
```

然后用 Secret 覆盖文件启动：

```powershell
docker compose -f compose.yml -f compose.deepseek.yml up --build -d
```

阶段 0 的 `/api/v1/system/deepseek/probe` 可验证用户提供的 OpenAI SDK 兼容调用方式。未配置 Secret 不影响基础三容器验收。不要运行会展开环境变量值的配置命令并把输出粘贴到公开日志。

## 文档

- [比赛版总体设计](./A07企业数据底座智能问析Agent系统_比赛版设计.md)
- [工程分阶段计划](./docs/engineering/PHASE_PLAN.md)
- [企业级扩展参考](./A07企业数据底座智能问析Agent系统_总体设计.md)

## Git 交付规则

每个阶段均遵循：开发分支 → 自动测试 → Docker 本地构建启动 → 用户测试确认 → 提交/打标签 → 推送 GitHub。未经用户确认，不推送远程仓库。
