# A07 工程分阶段与验收计划

## 1. 交付原则

每个阶段都是一个可独立启动、可测试、可回退的增量：

1. 在 `phase/xx-name` 分支开发；
2. 完成单元、接口和必要的浏览器测试；
3. 运行 `docker compose up --build -d`；
4. 提供明确的测试 URL、问题样例和预期结果；
5. 用户本地测试并明确确认；
6. 确认后提交阶段成果、创建阶段标签；
7. 已配置 GitHub remote 时才推送；未确认不得推送。

远程仓库地址、GitHub 登录或 Token 不写入项目文件。

## 2. 阶段总览

| 阶段 | 建议周期 | 主要成果 | Docker 验收门 |
|---|---:|---|---|
| 0. 工程初始化 | 1—2 天 | Git、Compose、Vue/FastAPI/PostgreSQL、DeepSeek 适配器骨架 | 三容器 healthy，首页和 API 正常 |
| 1. 数据与知识底座 | 第 1—3 周 | 9+1 表演示库、元数据目录、业务知识 CRUD、关系图 | 可浏览表字段、样例、指标与关系 |
| 2. 最薄 Agent 闭环 | 第 3—4 周 | DeepSeek + LangGraph，质量问题从提问到图表结论 | 一个质量问题完整实时运行 |
| 3. RAG + Text-to-SQL | 第 4—6 周 | 混合 RAG、EvidenceBundle、SQLGlot、只读执行与修复 | 15 个基础问题正确率达到门槛 |
| 4. 质量分析 | 第 7 周 | 良率、不良率、缺陷 Pareto、环比、质量简报 | 质量场景连续三次成功 |
| 5. 设备异常 | 第 8 周 | Recipe 模板、特征 SQL、Isolation Forest、偏离解释 | 设备场景连续三次成功 |
| 6. 生产与六算法 | 第 9—10 周 | 末工序产量、计划达成率、趋势斜率、六算法模板 | 三场景完整，六算法有验收用例 |
| 7. 评测与交付 | 第 11—12 周 | 30+12 测试集、安全、演示、PPT/视频/手册 | 无 P0 缺陷，8 分钟流程稳定 |

## 3. 阶段详细验收

### 阶段 0：工程初始化

交付：

- `main` 与 `phase/00-bootstrap` Git 分支；
- Web、App、PostgreSQL 三容器；
- `/api/health`、`/api/ready`、`/api/v1/system/bootstrap`；
- 可选 DeepSeek probe；
- 本文档和 PowerShell 冒烟脚本。

用户验收：

- <http://localhost:8080> 可见比赛版控制台；
- 页面显示数据库 Ready；
- <http://localhost:8000/docs> 可打开 API 文档；
- `test-stage0.ps1` 全部通过；
- 配置 DeepSeek Key 后 probe 返回有效回答。

### 阶段 1：数据与知识底座

交付 9 张主演示表、1 张留出表、固定业务日期、元数据扫描、字段样例、真实关系、三个业务主题和知识维护页面。验收重点是“不依赖手写前端常量即可展示数据库资源”。

### 阶段 2：最薄 Agent 闭环

只打通一个质量问题：理解 → 精确 schema 检索 → 计划 → SQL → 校验 → 执行 → 柱状图 → 结论。此阶段优先暴露端到端集成风险，不追求 RAG 完整度。

### 阶段 3：RAG + Text-to-SQL

交付业务知识、Schema、验证案例三路检索；精确/模糊/向量融合；SQLGlot 安全规则、只读账号、限行、超时、最多两次修复。金标问题与验证案例严格隔离。

### 阶段 4—6：三个制造场景

- 质量：工序良率、缺陷 Pareto、环比、简报；
- 设备：停机特征、Isolation Forest、特征偏离；
- 生产：末工序完工量、计划达成率、7 天趋势斜率；
- 六算法使用统一 Recipe 和审核模板，不建设 MLOps。

### 阶段 7：系统交付收口

本轮优先完成系统本身：问析质量门禁、多轮上下文追问、固定模板 CSV 数据导入、运行取消/重试、CSV/PNG 结果导出与歧义澄清。PPT、视频、演示编排和使用手册按当前范围暂缓，不纳入系统代码验收门。

## 4. Git 版本约定

| 阶段 | 分支 | 建议标签 |
|---|---|---|
| 0 | `phase/00-bootstrap` | `phase-0` |
| 1 | `phase/01-data-knowledge` | `phase-1` |
| 2 | `phase/02-agent-thin-slice` | `phase-2` |
| 3 | `phase/03-rag-text2sql` | `phase-3` |
| 4 | `phase/04-quality` | `phase-4` |
| 5 | `phase/05-equipment-anomaly` | `phase-5` |
| 6 | `phase/06-production-ml` | `phase-6` |
| 7 | `phase/07-delivery` | `v1.0.0-contest` |

提交信息采用 Conventional Commits，例如 `feat(agent): add thin-slice analysis graph`。阶段确认前允许修订，确认后标签保持不可变。
