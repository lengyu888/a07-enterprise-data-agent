# A07 企业数据底座智能问析 Agent

浙江省大学生服务外包创新应用大赛 A07 赛题的 12 周比赛版本实现。

核心技术主线：DeepSeek + LangGraph + 业务/Schema RAG + Text-to-SQL。

## 当前阶段

阶段 2：最薄 Agent 闭环（本地测试候选版，等待用户确认）。

- Vue 3 Web 工作台；
- FastAPI 模块化单体；
- PostgreSQL 16 + pgvector；
- 9 张主演示表 + 1 张未知 Schema 留出表，固定业务日期 `2025-12-29`；
- 约 11.8 万行可解释制造业数据，覆盖质量、设备、生产三个主题；
- PostgreSQL 表/字段/注释/样例/外键自动扫描与关系图；
- 业务主题、对象、指标、规则、同义词，以及指标口径 CRUD；
- DeepSeek 服务端适配器；
- LangGraph 八节点质量问析链路；
- 业务口径、强规则、Schema 与真实 Join 关系的精确证据检索；
- DeepSeek Text-to-SQL 与结构化输出契约；
- SQLGlot 单条只读 SQL、表白名单、语义字段、限行与时间边界校验；
- PostgreSQL 只读事务执行、5 秒超时与结果快照；
- Agent 轨迹、证据包、SQL、结果表、良率柱状图与有据结论；
- Docker Compose 本地构建、健康检查与验收脚本。

当前 MVP 只支持“分析本月各工序良率，找出良率最低的工序”。混合 RAG、通用 Text-to-SQL 与设备/生产场景将在后续阶段实现。

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

5. 执行当前阶段冒烟测试。

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\test-stage2.ps1
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

`/api/v1/system/deepseek/probe` 可验证用户提供的 OpenAI SDK 兼容调用方式。未配置 Secret 不影响基础三容器验收。不要运行会展开环境变量值的配置命令并把输出粘贴到公开日志。

## 阶段 2 Agent API

- `GET /api/v1/agent/capabilities`：MVP 场景、问题与八节点链路边界；
- `POST /api/v1/agent/runs`：执行真实质量问析；
- `GET /api/v1/agent/runs`：最近运行及审计状态。

阶段 1 的数据目录与业务知识 API 继续保留：

- `GET /api/v1/catalog/summary`：目录统计与固定业务日期；
- `GET /api/v1/catalog/tables`：数据表目录；
- `GET /api/v1/catalog/tables/{id}`：字段、类型、注释和样例；
- `GET /api/v1/catalog/relations`：真实外键关系；
- `POST /api/v1/catalog/refresh`：重新扫描 PostgreSQL 元数据；
- `GET /api/v1/knowledge/overview`：主题、规则和同义词；
- `GET/POST/PUT/DELETE /api/v1/knowledge/metrics`：指标口径维护。

## 文档

- [比赛版总体设计](./A07企业数据底座智能问析Agent系统_比赛版设计.md)
- [工程分阶段计划](./docs/engineering/PHASE_PLAN.md)
- [企业级扩展参考](./A07企业数据底座智能问析Agent系统_总体设计.md)

## Git 交付规则

每个阶段均遵循：开发分支 → 自动测试 → Docker 本地构建启动 → 用户测试确认 → 提交/打标签 → 推送 GitHub。未经用户确认，不推送远程仓库。
