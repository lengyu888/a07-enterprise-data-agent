# 阶段 5 测试报告

## 1. 交付范围

阶段 5“制造业设备异常专项”已经形成 Docker 本地测试候选版：

- 新增数据库审核 Recipe，固化算法、Feature SQL、特征、参数、训练/评分窗口和解释规则；
- 使用设备日粒度特征：停机总时长、停机次数、报警次数、平均/最大停机时长、计划事件占比、原因多样性；
- SQLGlot 校验 Feature SQL，只允许访问设备事件、设备维表和产线维表；
- PostgreSQL `EXPLAIN`、只读事务与 5 秒超时执行特征查询；
- 本地 `StandardScaler + IsolationForest`，固定 `n_estimators=200`、`contamination=0.03`、`random_state=42`；
- 以 2025-10-01 至 2025-11-30 的 549 个设备日作为训练基线；
- 对 2025-12-01 至 2025-12-29 的 261 个设备日评分；
- 使用设备历史中位数和 IQR 输出稳健特征偏离，只解释偏离、不宣称因果根因；
- 五节点 LangGraph：审核 Recipe/RAG、特征 SQL、Isolation Forest、偏离解释、DeepSeek 设备诊断；
- 新增亮色设备驾驶舱：九台设备排名、异常时间信号、偏离条、原因线索、Recipe 和完整轨迹；
- 新增报警次数、停机次数两项指标和通用 Text-to-SQL 问析。

## 2. 自动化与真实模型结果

| 项目 | 结果 |
|---|---|
| Docker 三容器 | healthy |
| API / Web 版本 | 0.6.0 |
| Vue TypeScript + Vite 生产构建 | 通过 |
| Python 编译检查 | 通过 |
| 算法 | scikit-learn Isolation Forest 1.7.1 |
| Recipe Feature SQL | SQLGlot + EXPLAIN + read-only 通过 |
| 历史训练样本 | 549 个设备日 |
| 当前评分样本 | 261 个设备日 |
| 设备排名 | 9/9 |
| Top 异常设备 | E08 / 热处理炉8 |
| Top 设备异常日 | 5/29 |
| 最大单次停机 | 145 分钟 |
| 主要特征偏离 | 停机总时长、平均停机、最大停机均 +3.06 IQR / +314.3% |
| 连续算法运行 | 3/3 completed，`passed=true` |
| 新增 RAG 指标 | `alarm_count`、`downtime_count` 均正确召回 |
| 报警次数 Text-to-SQL | 9 行，DeepSeek，0 次修复 |
| Playwright 桌面/移动端 | 通过 |
| 移动端横向溢出 | 无 |
| 浏览器控制台错误 | 0 |

## 3. Recipe 契约

| 项目 | 值 |
|---|---|
| Recipe | `equipment-daily-iforest-v1` |
| 算法版本 | 1.0 |
| 特征数 | 7 |
| 估计器 | 200 |
| 污染比例 | 0.03 |
| 随机种子 | 42 |
| 训练窗口 | 2025-10-01..2025-11-30 |
| 评分窗口 | 2025-12-01..2025-12-29 |
| 解释方法 | Median + IQR |

算法识别 E08 依赖设备事件中的持续停机行为，不读取预设设备答案。固定随机种子保证比赛演示可复现。

## 4. 本地验收

```powershell
docker compose up --build -d
# 打开工作台“模型配置 08”填写 Key 后继续
powershell -ExecutionPolicy Bypass -File .\scripts\test-stage5.ps1
```

浏览器测试：

```powershell
python .\tests\e2e\test_stage5_equipment_ui.py
```

测试入口：

- 工作台：<http://localhost:8080>
- API 文档：<http://localhost:8000/docs>
- 阶段验收：<http://localhost:8000/api/v1/agent/evaluation/stage5>

截图：

- `artifacts/stage5-equipment-desktop.png`
- `artifacts/stage5-equipment-mobile.png`

## 5. 建议用户验收动作

1. 打开“设备诊断”，点击“运行设备异常诊断”；
2. 确认 Top 异常设备为 `E08 / 热处理炉8`；
3. 核对异常日 5/29、最大单次停机 145 分钟和峰值评分 100；
4. 检查九台设备排名和时间信号上的五个异常点；
5. 检查前三个时长特征均相对历史中位数偏离 +314.3%；
6. 查看事件原因线索、DeepSeek 诊断、审核 Recipe 和五节点轨迹；
7. 点击“报警频次 / 停机次数 / 停机时长”进入通用问析并核对 SQL。

## 6. 阶段边界

- 不建设在线训练、模型注册中心或完整 MLOps；
- 算法输出为比赛数据中的行为偏离，不替代预测性维护平台；
- 事件原因只作为核查线索，不作为因果根因；
- 当前业务日期固定为 `2025-12-29`；
- 用户确认前，不提交阶段 5，不创建 `phase-5` 标签，不推送阶段 5 分支。
