# 阶段 2 测试报告

## 1. 交付范围

阶段 2“最薄 Agent 闭环”已经形成 Docker 本地测试候选版：

- 质量场景 MVP 问题：`分析本月各工序良率，找出良率最低的工序`；
- LangGraph 八节点：理解、检索、计划、Text-to-SQL、校验、执行、图表、结论；
- DeepSeek `deepseek-v4-pro` 结构化 SQL 生成与结论生成；
- 基于已发布指标、强规则、两张业务表和真实外键的精确证据包；
- SQLGlot 单 SELECT、DDL/DML 禁止、物理表白名单、业务语义字段、时间边界和限行校验；
- PostgreSQL 只读事务、5 秒语句超时、最多 100 行；
- 运行、步骤、SQL 产物和结果快照审计；
- 亮色智能问析工作台：轨迹、证据、SQL、表格、柱状图与结论。

## 2. 自动化结果

| 项目 | 结果 |
|---|---|
| Docker 三容器 | healthy |
| Vue TypeScript + Vite 生产构建 | 通过 |
| DeepSeek 真实 Text-to-SQL | 通过，非模板降级 |
| LangGraph 节点 | 8/8 完成 |
| SQL 物理表范围 | `demo.fact_quality_inspection`、`demo.dim_process` |
| SQL 安全状态 | SQLGlot passed |
| 只读与超时 | read-only / 5000 ms |
| 查询结果 | 3 个工序 |
| 最低良率结论 | 热处理，93.63% |
| Playwright 桌面端 | 通过 |
| Playwright 移动端 | 通过 |
| 浏览器控制台错误 | 0 |

## 3. 用户测试入口

- 工作台：<http://localhost:8080>
- API 文档：<http://localhost:8000/docs>
- Agent 能力边界：<http://localhost:8000/api/v1/agent/capabilities>
- 最近运行：<http://localhost:8000/api/v1/agent/runs>

本机验收命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-stage2.ps1
```

## 4. 建议验收动作

1. 打开“智能问析”，确认默认问题为阶段 2 唯一支持问题；
2. 点击“启动智能问析”，等待 30—90 秒；
3. 确认运行状态为 COMPLETED，SQL MODE 为 DEEPSEEK；
4. 确认轨迹显示 8/8 COMPLETED；
5. 确认证据包仅含良率口径、强规则、两张表和一条真实 Join；
6. 确认 SQLGLOT PASSED，SQL 只读且含明确日期范围；
7. 确认柱状图和表格包含热处理、精加工、终检包装三个工序；
8. 确认结论指出热处理良率最低，为 93.63%，且不臆测根因。

## 5. MVP 边界与阶段确认门

- 当前仅支持质量场景中的工序良率问题；
- 当前检索为确定性精确证据检索，不宣称已完成混合 RAG；
- 当前不支持自由跨域问题、设备异常和生产趋势；
- 失败运行会保留状态，安全校验失败不会执行 SQL；
- 用户确认前，不提交阶段 2，不创建 `phase-2` 标签，不推送该阶段分支。
