# A07 企业数据底座智能问析 Agent

浙江省大学生服务外包创新应用大赛 A07 赛题的 12 周比赛版本实现。

核心技术主线：DeepSeek + LangGraph + 业务/Schema RAG + Text-to-SQL。

## 当前阶段

阶段 6：生产趋势与六算法（Docker 本地测试候选版，等待用户确认）。

- Vue 3 Web 工作台；
- FastAPI 模块化单体；
- PostgreSQL 16 + pgvector；
- 9 张主演示表 + 1 张未知 Schema 留出表，固定业务日期 `2025-12-29`；
- 约 11.8 万行可解释制造业数据，覆盖质量、设备、生产三个主题；
- PostgreSQL 表/字段/注释/样例/外键自动扫描与关系图；
- 业务主题、对象、指标、规则、同义词，以及指标口径 CRUD；
- DeepSeek 服务端适配器；
- LangGraph 八节点通用问析、四节点质量简报，以及设备/生产五节点专项链路；
- 业务口径、强规则、Schema 与真实 Join 关系的精确证据检索；
- DeepSeek Text-to-SQL 与结构化输出契约；
- SQLGlot 单条只读 SQL、表白名单、语义字段、限行与时间边界校验；
- PostgreSQL 只读事务执行、5 秒超时与结果快照；
- Agent 轨迹、证据包、SQL、结果表、良率柱状图与有据结论；
- FastEmbed `BAAI/bge-small-zh-v1.5` 本地中文 embedding；
- 业务知识、Schema/关系、验证案例组成的 pgvector 索引；
- 精确匹配、pg_trgm 模糊匹配、pgvector 语义匹配三路 RRF 融合；
- 动态 EvidenceBundle，15 问必需表召回率 100%，上下文缩减约 70%；
- 质量、设备、生产三个场景的基础通用 Text-to-SQL；
- 质量专项的工序良率、缺陷 Pareto、30 天每日趋势与月度环比；
- 3 组 EvidenceBundle + 4 组只读 SQL + DeepSeek 的一键管理层质量简报；
- 审核 Recipe、设备日粒度 Feature SQL 与 SQLGlot 表白名单；
- 本地 Isolation Forest 设备异常检测，固定算法参数与随机种子；
- 历史中位数/IQR 特征偏离解释、九台设备排名和异常时间信号；
- 设备事件原因核查线索与 DeepSeek 可靠性诊断简报；
- 末工序完工量、计划达成率、29 日生产走势与产线排名；
- 最近七日 LinearRegression 斜率，严格标注为趋势描述而非未来预测；
- DeepSeek 生产运营简报、审核 Feature SQL、RAG 证据与节点轨迹；
- LinearRegression、LogisticRegression、DecisionTree、RandomForest、KMeans、IsolationForest 六个审核 Recipe；
- 六算法统一时间切分、固定随机种子、真实样本量和验收指标；
- SQL 校验/执行失败后最多两次 DeepSeek 修复回路；
- 柱状图、折线图、动态结果列与前端 RAG 检索台账；
- Docker Compose 本地构建、健康检查与验收脚本。

当前支持 20 个通用问析问题，质量、设备、生产三个场景均已形成专项闭环。比赛版不建设完整 MLOps，也不把七日趋势斜率包装为产量预测。

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

   当前比赛版本仅提供电脑网页端，统一推荐并按 `1440×900` 作为唯一桌面验收基准。小屏设备只显示桌面端访问提示。

5. 执行当前阶段冒烟测试。

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\test-stage6.ps1
   ```

6. 停止服务。

   ```powershell
   docker compose down
   ```

不要执行 `docker compose down -v`，除非确认要清空本地数据库卷。

## DeepSeek 配置

### 唯一配置方式：前端运行时配置

打开 <http://localhost:8080>，进入“模型配置 08”，填入 API Key 后点击“保存并验证连接”。Key 仅保存在 FastAPI 进程内存中，不写数据库、不回显、不进入 Git，Docker 重启后自动清除。

- `GET /api/v1/system/deepseek/config`：返回脱敏配置状态；
- `PUT /api/v1/system/deepseek/config`：设置并验证运行时 Key 与模型；
- `DELETE /api/v1/system/deepseek/config`：清除页面运行时 Key。

页面提供 `deepseek-v4-pro` 与 `deepseek-v4-flash` 两个当前有效模型。首次配置必须填写 Key；后续切换模型时可以留空沿用当前内存 Key。已弃用的 `deepseek-chat`、`deepseek-reasoner` 不进入选择列表。

系统不再读取 DeepSeek 环境变量、`.env` 或 Docker Secret。容器重启后必须在页面重新填写 Key。`/api/v1/system/deepseek/probe` 可单独验证 OpenAI SDK 兼容调用。

## 阶段 6 Agent / RAG / Algorithm API

- `GET /api/v1/agent/capabilities`：MVP 场景、问题与八节点链路边界；
- `POST /api/v1/agent/runs`：执行真实质量问析；
- `GET /api/v1/agent/runs`：最近运行及审计状态。
- `POST /api/v1/agent/quality/brief`：运行质量简报 LangGraph；
- `GET /api/v1/agent/evaluation/stage4`：质量场景连续成功门槛；
- `POST /api/v1/agent/equipment/diagnosis`：运行设备异常 Recipe 与五节点 LangGraph；
- `GET /api/v1/agent/evaluation/stage5`：设备算法连续成功门槛；
- `POST /api/v1/agent/production/trend`：运行生产趋势 Recipe 与五节点 LangGraph；
- `GET /api/v1/agent/algorithms`：查看六个已发布算法 Recipe；
- `POST /api/v1/agent/algorithms/evaluate`：执行六算法统一工程验收；
- `GET /api/v1/agent/evaluation/stage6`：生产连续成功与六算法验收门槛；
- `GET /api/v1/rag/status`：向量模型、索引类型与证据数量；
- `POST /api/v1/rag/search`：返回三路融合后的 EvidenceBundle；
- `POST /api/v1/rag/reindex`：增量重建知识索引。

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
