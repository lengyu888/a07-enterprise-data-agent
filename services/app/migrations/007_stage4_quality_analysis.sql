INSERT INTO app.metric
    (metric_code, topic_code, metric_name, description, formula, unit, grain,
     dimensions, mapped_tables, owner_name, version, status, updated_at)
VALUES
    ('defect_count', 'quality', '缺陷数量', '质量缺陷明细中各缺陷类型的数量之和，用于 Pareto 分析',
     'SUM(defect_qty)', '件', '日期×缺陷类型×缺陷等级',
     '["日期", "缺陷类型", "缺陷等级", "原因分类"]'::jsonb,
     '["demo.fact_quality_defect", "demo.fact_quality_inspection"]'::jsonb,
     '质量负责人', '1.0', 'published', NOW())
ON CONFLICT (metric_code) DO UPDATE SET
    metric_name=EXCLUDED.metric_name, description=EXCLUDED.description,
    formula=EXCLUDED.formula, unit=EXCLUDED.unit, grain=EXCLUDED.grain,
    dimensions=EXCLUDED.dimensions, mapped_tables=EXCLUDED.mapped_tables,
    version=EXCLUDED.version, status=EXCLUDED.status, updated_at=NOW();

INSERT INTO app.business_rule
    (rule_code, topic_code, rule_name, rule_content, severity, updated_at)
VALUES
    ('quality-defect-pareto-source', 'quality', '缺陷 Pareto 明细口径',
     '缺陷 Pareto 的缺陷数量只可汇总 fact_quality_defect.defect_qty；日期必须通过 inspection_id 连接 fact_quality_inspection.inspection_time 过滤。累计占比按缺陷数量降序计算，禁止将缺陷明细连接到检验表后计算良率。',
     'mandatory', NOW()),
    ('quality-period-compare', 'quality', '质量环比完整月份口径',
     '月度环比按数据锚点所在月与上一个自然月比较；当前月截至数据锚点 2025-12-29，上月使用 2025-11-01 至 2025-11-30，结果必须明确数据覆盖边界。',
     'mandatory', NOW())
ON CONFLICT (rule_code) DO UPDATE SET
    rule_name=EXCLUDED.rule_name, rule_content=EXCLUDED.rule_content,
    severity=EXCLUDED.severity, updated_at=NOW();

INSERT INTO app.synonym (topic_code, canonical_term, synonym_term) VALUES
    ('quality', '缺陷数量', '缺陷数'),
    ('quality', '缺陷数量', '缺陷 Pareto'),
    ('quality', '缺陷数量', '帕累托'),
    ('quality', '良率', '质量趋势'),
    ('quality', '良率', '质量环比')
ON CONFLICT DO NOTHING;

INSERT INTO app.validation_case
    (case_code, scene, question, metric_code, sql_template, expected_tables, notes)
VALUES
    ('quality-defect-pareto', 'quality', '本月缺陷类型 Pareto 分析', 'defect_count',
     'WITH defect_summary AS (SELECT d.defect_type, SUM(d.defect_qty) AS defect_count FROM demo.fact_quality_defect d JOIN demo.fact_quality_inspection q ON q.inspection_id=d.inspection_id WHERE q.inspection_time::date BETWEEN DATE ''2025-12-01'' AND DATE ''2025-12-29'' GROUP BY d.defect_type), ranked AS (SELECT defect_type, defect_count, ROUND(100.0 * SUM(defect_count) OVER (ORDER BY defect_count DESC, defect_type) / NULLIF(SUM(defect_count) OVER (), 0), 2) AS cumulative_share FROM defect_summary) SELECT defect_type, defect_count, cumulative_share FROM ranked ORDER BY defect_count DESC, defect_type LIMIT 100',
     '["demo.fact_quality_defect", "demo.fact_quality_inspection"]', '缺陷数量降序并返回累计占比'),
    ('quality-yield-daily', 'quality', '最近30天每日良率趋势', 'yield_rate',
     'SELECT q.inspection_time::date AS business_date, ROUND(100.0 * SUM(q.qualified_qty) / NULLIF(SUM(q.inspected_qty), 0), 2) AS yield_rate FROM demo.fact_quality_inspection q WHERE q.inspection_time::date BETWEEN DATE ''2025-11-30'' AND DATE ''2025-12-29'' GROUP BY q.inspection_time::date ORDER BY business_date LIMIT 100',
     '["demo.fact_quality_inspection"]', '按业务日聚合质量检验数据'),
    ('quality-yield-monthly-compare', 'quality', '对比本月与上月总体良率', 'yield_rate',
     'SELECT TO_CHAR(DATE_TRUNC(''month'', q.inspection_time), ''YYYY-MM'') AS business_month, ROUND(100.0 * SUM(q.qualified_qty) / NULLIF(SUM(q.inspected_qty), 0), 2) AS yield_rate FROM demo.fact_quality_inspection q WHERE q.inspection_time::date BETWEEN DATE ''2025-11-01'' AND DATE ''2025-12-29'' GROUP BY DATE_TRUNC(''month'', q.inspection_time) ORDER BY DATE_TRUNC(''month'', q.inspection_time) LIMIT 100',
     '["demo.fact_quality_inspection"]', '返回上月和当前月截至锚点的整体良率')
ON CONFLICT (case_code) DO UPDATE SET
    question=EXCLUDED.question, metric_code=EXCLUDED.metric_code,
    sql_template=EXCLUDED.sql_template, expected_tables=EXCLUDED.expected_tables,
    notes=EXCLUDED.notes, updated_at=NOW();

INSERT INTO app.app_config (config_key, config_value, updated_at) VALUES
    ('project_stage', '"phase-4"'::jsonb, NOW()),
    ('rag_index_version', '"stage4-quality-v1"'::jsonb, NOW())
ON CONFLICT (config_key) DO UPDATE SET config_value=EXCLUDED.config_value, updated_at=NOW();
