CREATE TABLE IF NOT EXISTS app.analysis_recipe (
    recipe_code TEXT PRIMARY KEY,
    scene TEXT NOT NULL CHECK (scene IN ('quality', 'equipment', 'production')),
    recipe_name TEXT NOT NULL,
    algorithm_name TEXT NOT NULL,
    version TEXT NOT NULL,
    feature_sql TEXT NOT NULL,
    feature_columns JSONB NOT NULL,
    parameters JSONB NOT NULL,
    training_window TEXT NOT NULL,
    scoring_window TEXT NOT NULL,
    explanation_rule TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('draft', 'published', 'disabled')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.algorithm_run (
    run_id UUID PRIMARY KEY,
    recipe_code TEXT NOT NULL REFERENCES app.analysis_recipe(recipe_code),
    scene TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    input_rows INTEGER NOT NULL DEFAULT 0,
    anomaly_rows INTEGER NOT NULL DEFAULT 0,
    top_entity TEXT,
    model_version TEXT,
    error_message TEXT,
    duration_ms INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

INSERT INTO app.analysis_recipe
    (recipe_code, scene, recipe_name, algorithm_name, version, feature_sql,
     feature_columns, parameters, training_window, scoring_window, explanation_rule, status, updated_at)
VALUES
    ('equipment-daily-iforest-v1', 'equipment', '设备日粒度停机异常识别', 'IsolationForest', '1.0',
     'WITH days AS (SELECT day::date AS business_date FROM generate_series(DATE ''2025-10-01'', DATE ''2025-12-29'', INTERVAL ''1 day'') day), grid AS (SELECT d.business_date, e.equipment_id, e.equipment_name, e.equipment_type, l.line_name FROM days d CROSS JOIN demo.dim_equipment e JOIN demo.dim_line l ON l.line_id=e.line_id), daily AS (SELECT v.start_time::date AS business_date, v.equipment_id, COALESCE(SUM(v.duration_minutes) FILTER (WHERE v.event_type=''downtime'' AND v.is_planned=false), 0) AS downtime_minutes, COUNT(*) FILTER (WHERE v.event_type=''downtime'' AND v.is_planned=false) AS downtime_count, COUNT(*) FILTER (WHERE v.event_type=''alarm'') AS alarm_count, COALESCE(AVG(v.duration_minutes) FILTER (WHERE v.event_type=''downtime'' AND v.is_planned=false), 0) AS avg_downtime_minutes, COALESCE(MAX(v.duration_minutes) FILTER (WHERE v.event_type=''downtime'' AND v.is_planned=false), 0) AS max_downtime_minutes, ROUND(COUNT(*) FILTER (WHERE v.is_planned)::numeric / NULLIF(COUNT(*), 0), 4) AS planned_event_ratio, COUNT(DISTINCT v.event_reason) AS reason_diversity FROM demo.fact_equipment_event v WHERE v.start_time::date BETWEEN DATE ''2025-10-01'' AND DATE ''2025-12-29'' GROUP BY v.start_time::date, v.equipment_id) SELECT g.business_date, g.equipment_id, g.equipment_name, g.equipment_type, g.line_name, COALESCE(d.downtime_minutes, 0) AS downtime_minutes, COALESCE(d.downtime_count, 0) AS downtime_count, COALESCE(d.alarm_count, 0) AS alarm_count, COALESCE(d.avg_downtime_minutes, 0) AS avg_downtime_minutes, COALESCE(d.max_downtime_minutes, 0) AS max_downtime_minutes, COALESCE(d.planned_event_ratio, 0) AS planned_event_ratio, COALESCE(d.reason_diversity, 0) AS reason_diversity FROM grid g LEFT JOIN daily d ON d.business_date=g.business_date AND d.equipment_id=g.equipment_id ORDER BY g.business_date, g.equipment_id',
     '["downtime_minutes", "downtime_count", "alarm_count", "avg_downtime_minutes", "max_downtime_minutes", "planned_event_ratio", "reason_diversity"]'::jsonb,
     '{"n_estimators": 200, "contamination": 0.03, "random_state": 42}'::jsonb,
     '2025-10-01..2025-11-30', '2025-12-01..2025-12-29',
     '异常日按 Isolation Forest decision_function 识别；偏离解释使用当前异常特征相对设备历史中位数和 IQR 的稳健偏离，仅解释数据偏离，不宣称因果根因。',
     'published', NOW())
ON CONFLICT (recipe_code) DO UPDATE SET
    recipe_name=EXCLUDED.recipe_name, algorithm_name=EXCLUDED.algorithm_name,
    version=EXCLUDED.version, feature_sql=EXCLUDED.feature_sql,
    feature_columns=EXCLUDED.feature_columns, parameters=EXCLUDED.parameters,
    training_window=EXCLUDED.training_window, scoring_window=EXCLUDED.scoring_window,
    explanation_rule=EXCLUDED.explanation_rule, status=EXCLUDED.status, updated_at=NOW();

INSERT INTO app.metric
    (metric_code, topic_code, metric_name, description, formula, unit, grain,
     dimensions, mapped_tables, owner_name, version, status, updated_at)
VALUES
    ('alarm_count', 'equipment', '报警次数', '设备报警事件数量',
     'COUNT(*) FILTER (WHERE event_type = ''alarm'')', '次', '日期×设备',
     '["日期", "设备", "产线", "原因"]'::jsonb,
     '["demo.fact_equipment_event"]'::jsonb, '设备负责人', '1.0', 'published', NOW()),
    ('downtime_count', 'equipment', '停机次数', '非计划停机事件数量',
     'COUNT(*) FILTER (WHERE event_type = ''downtime'' AND is_planned = false)', '次', '日期×设备',
     '["日期", "设备", "产线", "原因"]'::jsonb,
     '["demo.fact_equipment_event"]'::jsonb, '设备负责人', '1.0', 'published', NOW())
ON CONFLICT (metric_code) DO UPDATE SET
    metric_name=EXCLUDED.metric_name, description=EXCLUDED.description,
    formula=EXCLUDED.formula, unit=EXCLUDED.unit, grain=EXCLUDED.grain,
    dimensions=EXCLUDED.dimensions, mapped_tables=EXCLUDED.mapped_tables,
    version=EXCLUDED.version, status=EXCLUDED.status, updated_at=NOW();

INSERT INTO app.business_rule
    (rule_code, topic_code, rule_name, rule_content, severity, updated_at)
VALUES
    ('equipment-iforest-recipe', 'equipment', '设备异常审核 Recipe',
     'Isolation Forest 只使用已发布 Recipe 中的设备日粒度特征；训练窗口为 2025-10-01 至 2025-11-30，评分窗口为 2025-12-01 至 2025-12-29，random_state 固定为 42，结果必须附带版本和特征偏离解释。',
     'mandatory', NOW()),
    ('equipment-anomaly-not-cause', 'equipment', '异常偏离不等于根因',
     '算法只能说明设备行为相对历史基线的特征偏离；根因必须通过设备、工艺或维修记录进一步核查，DeepSeek 不得把事件原因分布直接宣称为因果根因。',
     'mandatory', NOW())
ON CONFLICT (rule_code) DO UPDATE SET
    rule_name=EXCLUDED.rule_name, rule_content=EXCLUDED.rule_content,
    severity=EXCLUDED.severity, updated_at=NOW();

INSERT INTO app.synonym (topic_code, canonical_term, synonym_term) VALUES
    ('equipment', '报警次数', '报警频次'),
    ('equipment', '停机次数', '停机频次'),
    ('equipment', '设备异常', '异常设备'),
    ('equipment', '设备异常', '离群设备'),
    ('equipment', '设备异常', 'Isolation Forest')
ON CONFLICT DO NOTHING;

INSERT INTO app.validation_case
    (case_code, scene, question, metric_code, sql_template, expected_tables, notes)
VALUES
    ('equipment-alarm-count', 'equipment', '本月各设备报警次数排名', 'alarm_count',
     'SELECT e.equipment_name, COUNT(*) FILTER (WHERE v.event_type=''alarm'') AS alarm_count FROM demo.fact_equipment_event v JOIN demo.dim_equipment e ON e.equipment_id=v.equipment_id WHERE v.start_time::date BETWEEN DATE ''2025-12-01'' AND DATE ''2025-12-29'' GROUP BY e.equipment_name ORDER BY alarm_count DESC, e.equipment_name LIMIT 100',
     '["demo.fact_equipment_event", "demo.dim_equipment"]', '报警事件按设备聚合'),
    ('equipment-downtime-count', 'equipment', '本月各设备非计划停机次数排名', 'downtime_count',
     'SELECT e.equipment_name, COUNT(*) FILTER (WHERE v.event_type=''downtime'' AND v.is_planned=false) AS downtime_count FROM demo.fact_equipment_event v JOIN demo.dim_equipment e ON e.equipment_id=v.equipment_id WHERE v.start_time::date BETWEEN DATE ''2025-12-01'' AND DATE ''2025-12-29'' GROUP BY e.equipment_name ORDER BY downtime_count DESC, e.equipment_name LIMIT 100',
     '["demo.fact_equipment_event", "demo.dim_equipment"]', '仅统计非计划停机事件')
ON CONFLICT (case_code) DO UPDATE SET
    question=EXCLUDED.question, metric_code=EXCLUDED.metric_code,
    sql_template=EXCLUDED.sql_template, expected_tables=EXCLUDED.expected_tables,
    notes=EXCLUDED.notes, updated_at=NOW();

INSERT INTO app.app_config (config_key, config_value, updated_at) VALUES
    ('project_stage', '"phase-5"'::jsonb, NOW()),
    ('rag_index_version', '"stage5-equipment-v1"'::jsonb, NOW())
ON CONFLICT (config_key) DO UPDATE SET config_value=EXCLUDED.config_value, updated_at=NOW();
