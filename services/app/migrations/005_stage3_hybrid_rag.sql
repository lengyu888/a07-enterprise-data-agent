CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS app.validation_case (
    case_code TEXT PRIMARY KEY,
    scene TEXT NOT NULL CHECK (scene IN ('quality', 'equipment', 'production')),
    question TEXT NOT NULL,
    metric_code TEXT NOT NULL REFERENCES app.metric(metric_code),
    sql_template TEXT NOT NULL,
    expected_tables JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.knowledge_chunk (
    id BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('business', 'schema', 'relation', 'example')),
    source_id TEXT NOT NULL,
    topic_code TEXT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    content_hash TEXT NOT NULL,
    embedding vector(512),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_type, source_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_content_trgm
    ON app.knowledge_chunk USING gin (content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_title_trgm
    ON app.knowledge_chunk USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_embedding_hnsw
    ON app.knowledge_chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_topic
    ON app.knowledge_chunk (topic_code, source_type);

INSERT INTO app.validation_case
    (case_code, scene, question, metric_code, sql_template, expected_tables, notes)
VALUES
    ('quality-yield-process', 'quality', '本月各工序良率对比', 'yield_rate',
     'SELECT p.process_name, ROUND(100.0 * SUM(q.qualified_qty) / NULLIF(SUM(q.inspected_qty), 0), 2) AS yield_rate, SUM(q.inspected_qty) AS inspected_qty FROM demo.fact_quality_inspection q JOIN demo.dim_process p ON p.process_id=q.process_id WHERE q.inspection_time::date BETWEEN DATE ''2025-12-01'' AND DATE ''2025-12-29'' GROUP BY p.process_name ORDER BY yield_rate ASC LIMIT 100',
     '["demo.fact_quality_inspection", "demo.dim_process"]', '返回全部工序，最低项排在第一行'),
    ('quality-yield-product', 'quality', '本月各产品良率排名', 'yield_rate',
     'SELECT p.product_name, ROUND(100.0 * SUM(q.qualified_qty) / NULLIF(SUM(q.inspected_qty), 0), 2) AS yield_rate FROM demo.fact_quality_inspection q JOIN demo.dim_product p ON p.product_id=q.product_id WHERE q.inspection_time::date BETWEEN DATE ''2025-12-01'' AND DATE ''2025-12-29'' GROUP BY p.product_name ORDER BY yield_rate ASC LIMIT 100',
     '["demo.fact_quality_inspection", "demo.dim_product"]', '按产品聚合'),
    ('quality-defect-process', 'quality', '本月各工序不良率', 'defect_rate',
     'SELECT p.process_name, ROUND(100.0 * (1 - SUM(q.qualified_qty)::numeric / NULLIF(SUM(q.inspected_qty), 0)), 2) AS defect_rate FROM demo.fact_quality_inspection q JOIN demo.dim_process p ON p.process_id=q.process_id WHERE q.inspection_time::date BETWEEN DATE ''2025-12-01'' AND DATE ''2025-12-29'' GROUP BY p.process_name ORDER BY defect_rate DESC LIMIT 100',
     '["demo.fact_quality_inspection", "demo.dim_process"]', '禁止连接缺陷明细计算不良率'),
    ('equipment-downtime-equipment', 'equipment', '本月各设备非计划停机时长', 'downtime_minutes',
     'SELECT e.equipment_name, ROUND(SUM(v.duration_minutes), 2) AS downtime_minutes FROM demo.fact_equipment_event v JOIN demo.dim_equipment e ON e.equipment_id=v.equipment_id WHERE v.event_type=''downtime'' AND v.is_planned=false AND v.start_time::date BETWEEN DATE ''2025-12-01'' AND DATE ''2025-12-29'' GROUP BY e.equipment_name ORDER BY downtime_minutes DESC LIMIT 100',
     '["demo.fact_equipment_event", "demo.dim_equipment"]', '仅非计划停机'),
    ('equipment-downtime-reason', 'equipment', '本月非计划停机原因排名', 'downtime_minutes',
     'SELECT v.event_reason, ROUND(SUM(v.duration_minutes), 2) AS downtime_minutes FROM demo.fact_equipment_event v WHERE v.event_type=''downtime'' AND v.is_planned=false AND v.start_time::date BETWEEN DATE ''2025-12-01'' AND DATE ''2025-12-29'' GROUP BY v.event_reason ORDER BY downtime_minutes DESC LIMIT 100',
     '["demo.fact_equipment_event"]', '按原因聚合'),
    ('equipment-downtime-trend', 'equipment', '最近30天非计划停机趋势', 'downtime_minutes',
     'SELECT v.start_time::date AS business_date, ROUND(SUM(v.duration_minutes), 2) AS downtime_minutes FROM demo.fact_equipment_event v WHERE v.event_type=''downtime'' AND v.is_planned=false AND v.start_time::date BETWEEN DATE ''2025-11-30'' AND DATE ''2025-12-29'' GROUP BY v.start_time::date ORDER BY business_date LIMIT 100',
     '["demo.fact_equipment_event"]', '按业务日聚合'),
    ('production-output-line', 'production', '本月各产线完工产量', 'final_output',
     'SELECT l.line_name, SUM(o.completed_qty) AS final_output FROM demo.fact_process_output o JOIN demo.dim_line l ON l.line_id=o.line_id WHERE o.is_final_process=true AND o.output_date BETWEEN DATE ''2025-12-01'' AND DATE ''2025-12-29'' GROUP BY l.line_name ORDER BY final_output DESC LIMIT 100',
     '["demo.fact_process_output", "demo.dim_line"]', '只统计末工序'),
    ('production-attainment-line', 'production', '本月各产线计划达成率', 'plan_attainment',
     'WITH actual AS (SELECT work_order_id, line_id, SUM(completed_qty) AS completed_qty FROM demo.fact_process_output WHERE is_final_process=true AND output_date BETWEEN DATE ''2025-12-01'' AND DATE ''2025-12-29'' GROUP BY work_order_id, line_id) SELECT l.line_name, ROUND(100.0 * SUM(a.completed_qty) / NULLIF(SUM(w.planned_qty), 0), 2) AS plan_attainment FROM actual a JOIN demo.fact_work_order w ON w.work_order_id=a.work_order_id JOIN demo.dim_line l ON l.line_id=a.line_id GROUP BY l.line_name ORDER BY plan_attainment DESC LIMIT 100',
     '["demo.fact_process_output", "demo.fact_work_order", "demo.dim_line"]', '计划量不可因工序明细重复'),
    ('production-output-trend', 'production', '最近30天完工产量趋势', 'final_output',
     'SELECT o.output_date AS business_date, SUM(o.completed_qty) AS final_output FROM demo.fact_process_output o WHERE o.is_final_process=true AND o.output_date BETWEEN DATE ''2025-11-30'' AND DATE ''2025-12-29'' GROUP BY o.output_date ORDER BY business_date LIMIT 100',
     '["demo.fact_process_output"]', '按业务日聚合且只统计末工序')
ON CONFLICT (case_code) DO UPDATE SET
    question=EXCLUDED.question, metric_code=EXCLUDED.metric_code,
    sql_template=EXCLUDED.sql_template, expected_tables=EXCLUDED.expected_tables,
    notes=EXCLUDED.notes, updated_at=NOW();

INSERT INTO app.app_config (config_key, config_value, updated_at) VALUES
    ('project_stage', '"phase-3"'::jsonb, NOW()),
    ('rag_index_version', '"stage3-v1"'::jsonb, NOW())
ON CONFLICT (config_key) DO UPDATE SET config_value=EXCLUDED.config_value, updated_at=NOW();
