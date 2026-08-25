# 阶段 3 测试报告

## 1. 交付范围

阶段 3“混合 RAG + 通用 Text-to-SQL”已经形成 Docker 本地测试候选版：

- 本地中文向量模型：FastEmbed `BAAI/bge-small-zh-v1.5`，512 维；
- pgvector HNSW、pg_trgm 与精确匹配三路检索，经 RRF 融合；
- 业务知识、数据表、字段、真实关系和验证案例组成 EvidenceBundle；
- 42 条向量证据：11 业务、10 Schema、12 关系、9 验证案例；
- 质量、设备、生产三个场景，5 个已发布指标和 15 个基础问题；
- 通用 DeepSeek 规划、Text-to-SQL、SQLGlot 校验、EXPLAIN、只读执行；
- 校验或执行失败后最多两次 DeepSeek SQL 修复；
- 动态柱状图/折线图、结果列、RAG 台账与证据来源展示；
- 指标维护后仅对变化知识块重新生成 embedding。

## 2. 自动化与真实模型结果

| 项目 | 结果 |
|---|---|
| Docker 三容器 | healthy |
| Vue TypeScript + Vite 生产构建 | 通过 |
| RAG 索引 | ready，42/42 已向量化 |
| Embedding | BGE 中文模型，512 维，本地 CPU |
| 检索通道 | exact + pg_trgm + pgvector |
| 融合策略 | Reciprocal Rank Fusion |
| 15 问指标召回 | 15/15 |
| 15 问必需表召回 | 15/15 |
| EvidenceBundle 上下文缩减 | 约 70% |
| 15 问真实 DeepSeek 端到端运行 | 15/15 completed |
| SQL 安全 | 表/字段/Join/口径/日期/限行校验通过 |
| SQL 执行 | EXPLAIN + read-only + 5000ms |
| 柱状图与 30 天折线图 | 通过 |
| 提示词注入/破坏性请求 | 生成前 422 拒绝 |
| Playwright 桌面/移动端 | 通过 |
| 浏览器控制台错误 | 0 |

## 3. 三场景代表性结果

| 场景 | 问题 | 结果形状 | 表范围 |
|---|---|---|---|
| 质量 | 本月各产品合格率排名 | 4 行柱状图 | 质量检验 + 产品维表 |
| 质量 | 本月各工序不良率 | 3 行柱状图 | 质量检验 + 工序维表 |
| 设备 | 各设备非计划停机时长 | 9 行柱状图 | 设备事件 + 设备维表 |
| 设备 | 最近 30 天停机趋势 | 30 行折线图 | 设备事件 |
| 生产 | 各产线计划达成率 | 3 行柱状图 | 工序产出 + 工单 + 产线维表 |
| 生产 | 最近 30 天完工产量 | 30 行折线图 | 工序产出 |

## 4. 用户测试入口

- 工作台：<http://localhost:8080>
- API 文档：<http://localhost:8000/docs>
- RAG 状态：<http://localhost:8000/api/v1/rag/status>
- Agent 能力：<http://localhost:8000/api/v1/agent/capabilities>

本机验收：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-stage3.ps1
```

## 5. 建议验收动作

1. 打开“智能问析”，在质量、设备、生产三个快捷问题之间切换；
2. 运行任一问题，确认 RAG 台账显示 exact、fuzzy、vector 三路命中；
3. 确认上下文缩减约 70%，EvidenceBundle 只包含相关表；
4. 确认执行轨迹可显示 SQL 修复节点，但最多不超过 2 次；
5. 确认 SQL 标识包含 SQLGLOT PASSED 与 REPAIR n/2；
6. 运行设备/生产趋势问题，确认生成 30 点折线图；
7. 在 API 文档提交破坏性问题，确认返回 422 且不生成 SQL。

## 6. 阶段边界

- 本阶段验证三个场景的基础查询能力，不实现缺陷 Pareto、Isolation Forest 或趋势预测；
- 验证案例只用于检索增强，与 `tests/gold/stage3_questions.json` 金标问题分开维护；
- 当前演示数据业务日期固定为 `2025-12-29`；
- 用户确认前，不提交阶段 3，不创建 `phase-3` 标签，不推送阶段 3 分支。
