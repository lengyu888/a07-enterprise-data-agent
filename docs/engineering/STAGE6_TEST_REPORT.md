# Stage 6 生产趋势与六算法验收报告

## 1. 验收信息

| 项目 | 结果 |
|---|---|
| 验收日期 | 2026-08-26 |
| 分支 | `phase/06-production-ml` |
| API / Web 版本 | `0.7.0` |
| 数据业务锚点 | `2025-12-29` |
| Docker 服务 | PostgreSQL、App、Web 均为 `healthy` |
| 阶段门禁 | `phase-6`，生产连续成功 3 次，六算法 6/6 完成 |

## 2. 本阶段交付

- 新增 `production-7d-linear-trend-v1` 审核 Recipe；
- 新增生产五节点 LangGraph：RAG/Recipe → 安全 SQL → 七日斜率 → 达成评估 → DeepSeek 简报；
- 末工序完工量、计划达成率、三产线排名、29 日趋势、七日斜率全部来自 PostgreSQL 实时聚合；
- SQLGlot 单条查询、表白名单、EXPLAIN、只读事务与超时控制继续生效；
- 新增 LogisticRegression、DecisionTree、RandomForest、KMeans 四个 Recipe，并复用 LinearRegression、IsolationForest，形成六算法能力集；
- 新增六算法统一验收接口，返回数据切分、样本量、模型指标、参数边界；
- 新增生产趋势页面、算法验收台、桌面端与移动端交互；
- 生成式柱状图、折线图、Pareto 图以及三类场景趋势图统一补充横轴、纵轴、刻度和单位；
- 提高证据、规则、SQL、执行轨迹等小字号信息的可读性，并为英文标签和代码分别采用清晰字体栈；
- 保持比赛版边界：不引入 Kubernetes、多租户治理或完整 MLOps，不提供大模型任意代码执行。

## 3. 确定性业务结果

| 指标 | 验收结果 |
|---|---:|
| 本月末工序完工量 | 74,535 件 |
| 本月计划量 | 77,758 件 |
| 整体计划达成率 | 95.86% |
| 最佳达成产线 | L03 三号装配产线，96.83% |
| 关注产线 | L02 二号柔性产线，93.89% |
| L02 最近七日斜率 | -44.61 件/日 |
| 每日产量点数 | 29 |
| LangGraph 节点数 | 5 |

七日 LinearRegression 运行在 `trend_calculation` 模式，只描述短期方向。接口、页面和 Recipe 均明确显示“不是未来产量预测”。

## 4. 六算法验收结果

| 算法 | 场景 | 训练/验证样本 | 核心指标 |
|---|---|---:|---|
| LinearRegression | 生产 | 183 / 87 | MAE 13.06；R² 0.9077 |
| LogisticRegression | 质量 | 38,979 / 18,531 | Balanced Accuracy 0.6102；F1 0.3278 |
| DecisionTree | 质量 | 38,979 / 18,531 | Balanced Accuracy 0.6234；F1 0.3659 |
| RandomForest | 质量 | 38,979 / 18,531 | Balanced Accuracy 0.6234；F1 0.3659 |
| KMeans | 设备 | 810 / 不适用 | Silhouette 0.5100 |
| IsolationForest | 设备 | 549 / 261 | 异常 7 条；异常率 0.0268 |

“通过”表示审核 Recipe 可执行、数据切分有效、输出可复现且指标有限值，不表示所有模型已达到生产部署阈值。分类指标如实保留，答辩时用于说明模型选择和后续优化空间。

## 5. 自动化测试

| 测试 | 结果 |
|---|---|
| Docker 标准前端构建：`vue-tsc -b && vite build` | 通过 |
| 容器内 `python -m compileall -q app` | 通过 |
| `/api/health`、`/api/ready`、capabilities | 通过 |
| 六算法真实执行 | 6/6 通过，约 2.8 秒 |
| 生产趋势固定简报替身连续运行 | 3/3 通过，业务数据不外传 |
| `test_stage6_polish_ui.py` | 桌面/移动通过 |
| `test_stage6_production_ui.py` | 生产页、六算法、桌面/移动通过 |
| `test_stage6_chart_axes_ui.py` | 生成式柱状图/折线图坐标轴、单位、刻度及关键信息字号通过 |
| `test_stage6_model_settings_ui.py` | Pro/Flash 选择、运行时 Key、留空复用、响应脱敏、清除和移动端通过 |
| 390 × 844 横向溢出检查 | 通过 |
| 浏览器 Console Error | 0 |

自动验收没有把聚合生产数据发送给外部模型：生产 LangGraph 使用固定本地简报替身验证确定性节点。正式页面仍保留真实 DeepSeek 通道，由用户在“模型配置 08”填写运行时 Key 后手动确认。

## 6. 手工验收流程

1. 打开 <http://localhost:8080>；
2. 若顶部显示 DeepSeek 未配置，进入“模型配置 08”，填入 Key 并完成连接验证；
3. 进入“生产趋势”；
4. 点击“运行生产趋势问析”，确认显示 74,535 件、95.86%、L02 和 -44.61 件/日；
5. 查看 29 日折线、3 条产线排名、5 节点轨迹、Recipe SQL 与 DeepSeek 简报；
6. 点击“执行六算法验收”，确认显示 6/6；
7. 点击 SQL 下钻的“完工产量”“计划达成”“每日趋势”，确认进入智能问析并带入对应问题；
8. 可执行 `powershell -ExecutionPolicy Bypass -File .\scripts\test-stage6.ps1` 完成包含真实 DeepSeek 简报的连续验收。

## 7. 交付状态

- Stage 6 代码已在本地完成；
- Docker 三服务保持运行，可立即测试；
- 用户确认前，不提交、不创建 `phase-6` 标签、不推送本轮代码；
- 用户确认后提交并推送 `phase/06-production-ml`，再进入 Stage 7 评测与竞赛交付。
