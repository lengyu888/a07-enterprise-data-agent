# 阶段 4 测试报告

## 1. 交付范围

阶段 4“制造业质量分析专项”已经形成 Docker 本地测试候选版：

- 新增“缺陷数量”业务指标、两条质量强规则和质量同义词；
- 新增缺陷 Pareto、最近 30 天每日良率、月度良率环比三个验证案例；
- 三类专项问题继续通过通用 RAG、DeepSeek 规划/Text-to-SQL、SQLGlot 与只读执行链；
- 缺陷 Pareto 返回缺陷数量、单项占比和累计占比，并生成柱线组合图；
- 新增四节点 LangGraph 质量简报：证据检索、指标聚合、变化诊断、DeepSeek 简报；
- 新增亮色质量驾驶舱，集中显示 KPI、Pareto、趋势、工序短板、风险与建议动作；
- 保留一键下钻到通用智能问析，展示 SQL、EvidenceBundle 和完整 Agent 轨迹。

## 2. 自动化与真实模型结果

| 项目 | 结果 |
|---|---|
| Docker 三容器 | healthy |
| API / Web 版本 | 0.5.0 |
| Vue TypeScript + Vite 生产构建 | 通过 |
| 新增质量指标 | `defect_count` / 缺陷数量 |
| Pareto Text-to-SQL | completed，DeepSeek，0 次修复 |
| Pareto 数据 | 6 类，累计占比 100% |
| 每日良率趋势 | completed，30 个日期点 |
| 月度环比 | 95.97% → 94.78%，-1.19 个百分点 |
| 一键质量简报 | 3 组 RAG + 4 组只读 SQL + 4 个 LangGraph 节点 |
| 质量简报模式 | DeepSeek 结构化输出 |
| 连续成功门槛 | 3/3，`passed=true` |
| Playwright 桌面/移动端 | 通过 |
| 移动端横向溢出 | 无 |
| 浏览器控制台错误 | 0 |

## 3. 代表性真实结果

| 指标 | 结果 |
|---|---|
| 本月总体良率 | 94.78% |
| 上月总体良率 | 95.97% |
| 环比变化 | -1.19 个百分点 |
| 本月检验数量 | 1,404,167 件 |
| 最低良率工序 | 热处理，93.63% |
| 首要缺陷 | 尺寸偏差，29.73% |
| 关键缺陷集合 | 尺寸偏差、表面划伤、热处理硬度不足、外观污染、毛刺 |

数据边界固定为 `2025-12-01` 至 `2025-12-29`；上月环比使用 `2025-11-01` 至 `2025-11-30`。

## 4. 本地验收

启动容器后，先在“模型配置 08”填写 Key，再运行验收：

```powershell
docker compose up --build -d
powershell -ExecutionPolicy Bypass -File .\scripts\test-stage4.ps1
```

浏览器测试：

```powershell
python .\tests\e2e\test_stage4_quality_ui.py
```

测试入口：

- 工作台：<http://localhost:8080>
- API 文档：<http://localhost:8000/docs>
- 阶段验收：<http://localhost:8000/api/v1/agent/evaluation/stage4>

截图：

- `artifacts/stage4-quality-desktop.png`
- `artifacts/stage4-quality-mobile.png`

## 5. 建议用户验收动作

1. 打开“质量驾驶舱”，点击“生成本月质量简报”；
2. 核对 94.78% 良率、-1.19 pp 环比、热处理最低和尺寸偏差首要；
3. 检查 Pareto 累计占比、30 天趋势和三道工序良率；
4. 查看 DeepSeek 管理简报、风险观察、建议动作与四节点轨迹；
5. 点击“缺陷 Pareto / 每日良率趋势 / 月度环比”进入通用智能问析；
6. 核对 RAG 台账、SQLGLOT PASSED、只读 SQL 和 EvidenceBundle。

## 6. 阶段边界

- 本阶段只聚焦质量分析，不实现设备异常算法和生产预测；
- 简报建议仅提出核查与改进方向，不宣称从聚合数据中发现了因果根因；
- 当前数据为固定锚点的可解释比赛演示数据；
- 用户确认前，不提交阶段 4，不创建 `phase-4` 标签，不推送阶段 4 分支。
