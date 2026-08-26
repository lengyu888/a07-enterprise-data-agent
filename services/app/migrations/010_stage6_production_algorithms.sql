CREATE TABLE IF NOT EXISTS app.algorithm_evaluation_run (
    run_id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    dataset_anchor DATE NOT NULL,
    algorithm_count INTEGER NOT NULL DEFAULT 0,
    results JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT,
    duration_ms INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

INSERT INTO app.analysis_recipe
    (recipe_code, scene, recipe_name, algorithm_name, version, feature_sql,
     feature_columns, parameters, training_window, scoring_window, explanation_rule, status, updated_at)
VALUES
    ('production-7d-linear-trend-v1', 'production', '产线七日完工趋势斜率', 'LinearRegression', '1.0',
     'SELECT o.output_date AS business_date, l.line_id, l.line_name, SUM(o.completed_qty) AS final_output, SUM(w.planned_qty) AS planned_qty, ROUND(100.0 * SUM(o.completed_qty) / NULLIF(SUM(w.planned_qty), 0), 2) AS plan_attainment FROM demo.fact_process_output o JOIN demo.fact_work_order w ON w.work_order_id=o.work_order_id JOIN demo.dim_line l ON l.line_id=o.line_id WHERE o.is_final_process=true AND o.output_date BETWEEN DATE ''2025-10-01'' AND DATE ''2025-12-29'' GROUP BY o.output_date, l.line_id, l.line_name ORDER BY o.output_date, l.line_id',
     '["final_output", "planned_qty", "plan_attainment"]'::jsonb,
     '{"fit_days": 7, "random_state": 42, "mode": "trend_calculation"}'::jsonb,
     '2025-10-01..2025-12-22', '2025-12-23..2025-12-29',
     '只以最近七个业务日拟合线性斜率，单位为件/日，用于描述短期方向；不展示训练/验证集指标，不宣称具有产量预测能力。',
     'published', NOW()),
    ('quality-logistic-v1', 'quality', '质量风险二分类验收', 'LogisticRegression', '1.0',
     'SELECT q.inspection_time::date AS business_date, q.inspected_qty, p.process_sequence, CASE w.shift_code WHEN ''A'' THEN 1 WHEN ''B'' THEN 2 ELSE 3 END AS shift_no, SUBSTRING(w.product_id FROM 2)::int AS product_no, SUBSTRING(w.line_id FROM 2)::int AS line_no, CASE WHEN q.inspection_result=''fail'' THEN 1 ELSE 0 END AS target FROM demo.fact_quality_inspection q JOIN demo.fact_work_order w ON w.work_order_id=q.work_order_id JOIN demo.dim_process p ON p.process_id=q.process_id WHERE q.inspection_time::date BETWEEN DATE ''2025-10-01'' AND DATE ''2025-12-29'' ORDER BY q.inspection_time, q.inspection_id',
     '["inspected_qty", "process_sequence", "shift_no", "product_no", "line_no"]'::jsonb,
     '{"max_iter": 500, "class_weight": "balanced", "random_state": 42, "target": "fail"}'::jsonb,
     '2025-10-01..2025-11-30', '2025-12-01..2025-12-29',
     '按业务日期切分训练和验证集，输出 balanced accuracy 与 F1；仅证明固定模板可复现，不替代质量根因分析。',
     'published', NOW()),
    ('quality-decision-tree-v1', 'quality', '质量规则树验收', 'DecisionTree', '1.0',
     'SELECT q.inspection_time::date AS business_date, q.inspected_qty, p.process_sequence, CASE w.shift_code WHEN ''A'' THEN 1 WHEN ''B'' THEN 2 ELSE 3 END AS shift_no, SUBSTRING(w.product_id FROM 2)::int AS product_no, SUBSTRING(w.line_id FROM 2)::int AS line_no, CASE WHEN q.inspection_result=''fail'' THEN 1 ELSE 0 END AS target FROM demo.fact_quality_inspection q JOIN demo.fact_work_order w ON w.work_order_id=q.work_order_id JOIN demo.dim_process p ON p.process_id=q.process_id WHERE q.inspection_time::date BETWEEN DATE ''2025-10-01'' AND DATE ''2025-12-29'' ORDER BY q.inspection_time, q.inspection_id',
     '["inspected_qty", "process_sequence", "shift_no", "product_no", "line_no"]'::jsonb,
     '{"max_depth": 5, "min_samples_leaf": 20, "class_weight": "balanced", "random_state": 42, "target": "fail"}'::jsonb,
     '2025-10-01..2025-11-30', '2025-12-01..2025-12-29',
     '固定树深和叶节点样本数，按时间留出验证，展示 balanced accuracy、F1 与树深。',
     'published', NOW()),
    ('quality-random-forest-v1', 'quality', '质量集成分类验收', 'RandomForest', '1.0',
     'SELECT q.inspection_time::date AS business_date, q.inspected_qty, p.process_sequence, CASE w.shift_code WHEN ''A'' THEN 1 WHEN ''B'' THEN 2 ELSE 3 END AS shift_no, SUBSTRING(w.product_id FROM 2)::int AS product_no, SUBSTRING(w.line_id FROM 2)::int AS line_no, CASE WHEN q.inspection_result=''fail'' THEN 1 ELSE 0 END AS target FROM demo.fact_quality_inspection q JOIN demo.fact_work_order w ON w.work_order_id=q.work_order_id JOIN demo.dim_process p ON p.process_id=q.process_id WHERE q.inspection_time::date BETWEEN DATE ''2025-10-01'' AND DATE ''2025-12-29'' ORDER BY q.inspection_time, q.inspection_id',
     '["inspected_qty", "process_sequence", "shift_no", "product_no", "line_no"]'::jsonb,
     '{"n_estimators": 120, "max_depth": 7, "min_samples_leaf": 10, "class_weight": "balanced", "random_state": 42, "target": "fail"}'::jsonb,
     '2025-10-01..2025-11-30', '2025-12-01..2025-12-29',
     '固定随机种子和树参数，按时间留出验证，展示 balanced accuracy 与 F1，特征重要度仅表示模型贡献。',
     'published', NOW()),
    ('equipment-daily-kmeans-v1', 'equipment', '设备行为分群验收', 'KMeans', '1.0',
     'SELECT v.start_time::date AS business_date, v.equipment_id, COALESCE(SUM(v.duration_minutes) FILTER (WHERE v.event_type=''downtime'' AND v.is_planned=false), 0) AS downtime_minutes, COUNT(*) FILTER (WHERE v.event_type=''downtime'' AND v.is_planned=false) AS downtime_count, COUNT(*) FILTER (WHERE v.event_type=''alarm'') AS alarm_count, COALESCE(MAX(v.duration_minutes), 0) AS max_duration FROM demo.fact_equipment_event v WHERE v.start_time::date BETWEEN DATE ''2025-10-01'' AND DATE ''2025-12-29'' GROUP BY v.start_time::date, v.equipment_id ORDER BY v.start_time::date, v.equipment_id',
     '["downtime_minutes", "downtime_count", "alarm_count", "max_duration"]'::jsonb,
     '{"n_clusters": 3, "n_init": 20, "random_state": 42}'::jsonb,
     '2025-10-01..2025-12-29', 'same_window_unsupervised',
     'StandardScaler 后执行三簇分群，输出 silhouette score 与各簇样本数；分群标签只表示相似行为，不代表风险等级。',
     'published', NOW())
ON CONFLICT (recipe_code) DO UPDATE SET
    recipe_name=EXCLUDED.recipe_name, algorithm_name=EXCLUDED.algorithm_name,
    version=EXCLUDED.version, feature_sql=EXCLUDED.feature_sql,
    feature_columns=EXCLUDED.feature_columns, parameters=EXCLUDED.parameters,
    training_window=EXCLUDED.training_window, scoring_window=EXCLUDED.scoring_window,
    explanation_rule=EXCLUDED.explanation_rule, status=EXCLUDED.status, updated_at=NOW();

INSERT INTO app.business_rule
    (rule_code, topic_code, rule_name, rule_content, severity, updated_at)
VALUES
    ('production-final-process-only', 'production', '生产产量只统计末工序',
     '完工产量必须过滤 is_final_process=true；计划量按工单汇总，禁止因工序明细连接造成重复累计。',
     'mandatory', NOW()),
    ('production-trend-not-forecast', 'production', '趋势斜率不等于预测',
     '七日线性回归仅用于描述短期变化方向，必须展示窗口和件/日单位，不得把趋势斜率包装成未来产量预测。',
     'mandatory', NOW()),
    ('algorithm-recipe-boundary', 'production', '比赛算法模板边界',
     '六类算法只能运行已发布 Recipe；固定特征、时间切分和随机种子，输出真实验收指标，不接受大模型生成任意训练代码。',
     'mandatory', NOW())
ON CONFLICT (rule_code) DO UPDATE SET
    rule_name=EXCLUDED.rule_name, rule_content=EXCLUDED.rule_content,
    severity=EXCLUDED.severity, updated_at=NOW();

INSERT INTO app.synonym (topic_code, canonical_term, synonym_term) VALUES
    ('production', '完工产量', '产出'),
    ('production', '完工产量', '实际产量'),
    ('production', '计划达成率', '计划完成率'),
    ('production', '生产趋势', '产量走势'),
    ('production', '生产趋势', '七日斜率')
ON CONFLICT DO NOTHING;

INSERT INTO app.validation_case
    (case_code, scene, question, metric_code, sql_template, expected_tables, notes)
VALUES
    ('production-final-output-rank', 'production', '本月各产线完工产量排名', 'final_output',
     'SELECT l.line_name, SUM(o.completed_qty) AS final_output FROM demo.fact_process_output o JOIN demo.dim_line l ON l.line_id=o.line_id WHERE o.is_final_process=true AND o.output_date BETWEEN DATE ''2025-12-01'' AND DATE ''2025-12-29'' GROUP BY l.line_name ORDER BY final_output DESC LIMIT 100',
     '["demo.fact_process_output", "demo.dim_line"]', '只统计末工序完工量'),
    ('production-plan-attainment', 'production', '本月各产线计划达成率', 'plan_attainment',
     'WITH actual AS (SELECT work_order_id, line_id, SUM(completed_qty) AS final_output FROM demo.fact_process_output WHERE is_final_process=true AND output_date BETWEEN DATE ''2025-12-01'' AND DATE ''2025-12-29'' GROUP BY work_order_id, line_id) SELECT l.line_name, ROUND(100.0*SUM(a.final_output)/NULLIF(SUM(w.planned_qty),0),2) AS plan_attainment FROM actual a JOIN demo.fact_work_order w ON w.work_order_id=a.work_order_id JOIN demo.dim_line l ON l.line_id=a.line_id GROUP BY l.line_name ORDER BY plan_attainment DESC LIMIT 100',
     '["demo.fact_process_output", "demo.fact_work_order", "demo.dim_line"]', '工单计划量不可重复')
ON CONFLICT (case_code) DO UPDATE SET
    question=EXCLUDED.question, metric_code=EXCLUDED.metric_code,
    sql_template=EXCLUDED.sql_template, expected_tables=EXCLUDED.expected_tables,
    notes=EXCLUDED.notes, updated_at=NOW();

INSERT INTO app.app_config (config_key, config_value, updated_at) VALUES
    ('project_stage', '"phase-6"'::jsonb, NOW()),
    ('rag_index_version', '"stage6-production-v1"'::jsonb, NOW())
ON CONFLICT (config_key) DO UPDATE SET config_value=EXCLUDED.config_value, updated_at=NOW();
