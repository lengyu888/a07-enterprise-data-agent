CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS demo;
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS demo.dim_product (
    product_id TEXT PRIMARY KEY,
    product_code TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    product_family TEXT NOT NULL,
    specification TEXT NOT NULL
);
COMMENT ON TABLE demo.dim_product IS '产品主数据：每行代表一个制造产品';
COMMENT ON COLUMN demo.dim_product.product_id IS '产品唯一标识';
COMMENT ON COLUMN demo.dim_product.product_code IS '产品编码';
COMMENT ON COLUMN demo.dim_product.product_name IS '产品名称';
COMMENT ON COLUMN demo.dim_product.product_family IS '产品系列';
COMMENT ON COLUMN demo.dim_product.specification IS '产品规格';

CREATE TABLE IF NOT EXISTS demo.dim_process (
    process_id TEXT PRIMARY KEY,
    process_code TEXT NOT NULL UNIQUE,
    process_name TEXT NOT NULL,
    process_sequence INTEGER NOT NULL CHECK (process_sequence > 0),
    is_final_process BOOLEAN NOT NULL DEFAULT FALSE
);
COMMENT ON TABLE demo.dim_process IS '工序主数据：每行代表一道标准生产工序';
COMMENT ON COLUMN demo.dim_process.process_sequence IS '工艺路线顺序';
COMMENT ON COLUMN demo.dim_process.is_final_process IS '是否为末工序';

CREATE TABLE IF NOT EXISTS demo.dim_line (
    line_id TEXT PRIMARY KEY,
    line_code TEXT NOT NULL UNIQUE,
    line_name TEXT NOT NULL,
    workshop_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'maintenance', 'idle'))
);
COMMENT ON TABLE demo.dim_line IS '产线主数据：每行代表一条制造产线';
COMMENT ON COLUMN demo.dim_line.workshop_name IS '所属车间';

CREATE TABLE IF NOT EXISTS demo.dim_equipment (
    equipment_id TEXT PRIMARY KEY,
    equipment_code TEXT NOT NULL UNIQUE,
    equipment_name TEXT NOT NULL,
    equipment_type TEXT NOT NULL,
    line_id TEXT NOT NULL REFERENCES demo.dim_line(line_id),
    commissioned_date DATE NOT NULL
);
COMMENT ON TABLE demo.dim_equipment IS '设备主数据：每行代表一台生产设备';
COMMENT ON COLUMN demo.dim_equipment.line_id IS '设备所属产线';

CREATE TABLE IF NOT EXISTS demo.fact_work_order (
    work_order_id TEXT PRIMARY KEY,
    order_no TEXT NOT NULL UNIQUE,
    plan_date DATE NOT NULL,
    product_id TEXT NOT NULL REFERENCES demo.dim_product(product_id),
    line_id TEXT NOT NULL REFERENCES demo.dim_line(line_id),
    planned_qty INTEGER NOT NULL CHECK (planned_qty > 0),
    shift_code TEXT NOT NULL CHECK (shift_code IN ('A', 'B', 'C')),
    order_status TEXT NOT NULL CHECK (order_status IN ('completed', 'running', 'planned'))
);
COMMENT ON TABLE demo.fact_work_order IS '生产工单事实：每行代表一个产线日生产工单，仅承载计划量';
COMMENT ON COLUMN demo.fact_work_order.plan_date IS '计划生产日期，也是工单业务日期';
COMMENT ON COLUMN demo.fact_work_order.planned_qty IS '计划生产数量';

CREATE TABLE IF NOT EXISTS demo.fact_process_output (
    output_id BIGINT PRIMARY KEY,
    work_order_id TEXT NOT NULL REFERENCES demo.fact_work_order(work_order_id),
    process_id TEXT NOT NULL REFERENCES demo.dim_process(process_id),
    line_id TEXT NOT NULL REFERENCES demo.dim_line(line_id),
    output_date DATE NOT NULL,
    completed_qty INTEGER NOT NULL CHECK (completed_qty >= 0),
    scrap_qty INTEGER NOT NULL CHECK (scrap_qty >= 0),
    rework_qty INTEGER NOT NULL CHECK (rework_qty >= 0),
    is_final_process BOOLEAN NOT NULL,
    UNIQUE (work_order_id, process_id)
);
COMMENT ON TABLE demo.fact_process_output IS '工序产量事实：每行代表某工单在某工序某日的汇总产出';
COMMENT ON COLUMN demo.fact_process_output.completed_qty IS '工序完工数量；统计总产量时仅使用末工序';
COMMENT ON COLUMN demo.fact_process_output.is_final_process IS '末工序标记，生产总量计算必须过滤为 true';

CREATE TABLE IF NOT EXISTS demo.fact_quality_inspection (
    inspection_id BIGINT PRIMARY KEY,
    work_order_id TEXT NOT NULL REFERENCES demo.fact_work_order(work_order_id),
    product_id TEXT NOT NULL REFERENCES demo.dim_product(product_id),
    process_id TEXT NOT NULL REFERENCES demo.dim_process(process_id),
    inspection_time TIMESTAMPTZ NOT NULL,
    inspected_qty INTEGER NOT NULL CHECK (inspected_qty > 0),
    qualified_qty INTEGER NOT NULL CHECK (qualified_qty >= 0 AND qualified_qty <= inspected_qty),
    inspection_result TEXT NOT NULL CHECK (inspection_result IN ('pass', 'warning', 'fail')),
    inspector_group TEXT NOT NULL
);
COMMENT ON TABLE demo.fact_quality_inspection IS '质量检验事实：每行代表一次产品/工序检验，是良率唯一事实来源';
COMMENT ON COLUMN demo.fact_quality_inspection.inspected_qty IS '检验数量';
COMMENT ON COLUMN demo.fact_quality_inspection.qualified_qty IS '合格数量；良率=合格数量/检验数量';

CREATE TABLE IF NOT EXISTS demo.fact_quality_defect (
    defect_record_id BIGINT PRIMARY KEY,
    inspection_id BIGINT NOT NULL REFERENCES demo.fact_quality_inspection(inspection_id),
    defect_type TEXT NOT NULL,
    defect_level TEXT NOT NULL CHECK (defect_level IN ('minor', 'major', 'critical')),
    defect_qty INTEGER NOT NULL CHECK (defect_qty > 0),
    cause_category TEXT NOT NULL,
    UNIQUE (inspection_id, defect_type)
);
COMMENT ON TABLE demo.fact_quality_defect IS '质量缺陷事实：每行代表一次检验中的一种缺陷汇总';
COMMENT ON COLUMN demo.fact_quality_defect.defect_type IS '缺陷类型，用于 Pareto 分析';
COMMENT ON COLUMN demo.fact_quality_defect.defect_qty IS '该类缺陷数量；禁止直接连接后计算检验良率';

CREATE TABLE IF NOT EXISTS demo.fact_equipment_event (
    event_id BIGINT PRIMARY KEY,
    equipment_id TEXT NOT NULL REFERENCES demo.dim_equipment(equipment_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('downtime', 'alarm')),
    event_code TEXT NOT NULL,
    event_reason TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    duration_minutes NUMERIC(10,2) NOT NULL CHECK (duration_minutes >= 0),
    is_planned BOOLEAN NOT NULL DEFAULT FALSE
);
COMMENT ON TABLE demo.fact_equipment_event IS '设备事件事实：每行代表一次停机或报警事件';
COMMENT ON COLUMN demo.fact_equipment_event.duration_minutes IS '事件持续分钟数，异常分析需先按设备和业务日聚合';

CREATE TABLE IF NOT EXISTS demo.fact_shift_summary (
    shift_summary_id BIGINT PRIMARY KEY,
    business_date DATE NOT NULL,
    shift_code TEXT NOT NULL CHECK (shift_code IN ('A', 'B', 'C')),
    line_id TEXT NOT NULL REFERENCES demo.dim_line(line_id),
    planned_qty INTEGER NOT NULL,
    completed_qty INTEGER NOT NULL,
    qualified_qty INTEGER NOT NULL,
    UNIQUE (business_date, shift_code, line_id)
);
COMMENT ON TABLE demo.fact_shift_summary IS '留出表：班次产量汇总，不预置任何问题-SQL案例';
COMMENT ON COLUMN demo.fact_shift_summary.business_date IS '班次业务日期';
COMMENT ON COLUMN demo.fact_shift_summary.shift_code IS '班次编码 A/B/C';

INSERT INTO demo.dim_product VALUES
    ('P01', 'P-100', '精密轴承 A', '轴承系列', '40mm'),
    ('P02', 'P-200', '精密轴承 B', '轴承系列', '60mm'),
    ('P03', 'P-300', '减速器壳体', '传动系列', 'R80'),
    ('P04', 'P-400', '伺服连接座', '伺服系列', 'S45')
ON CONFLICT DO NOTHING;

INSERT INTO demo.dim_process VALUES
    ('PR10', 'OP10', '精加工', 10, FALSE),
    ('PR20', 'OP20', '热处理', 20, FALSE),
    ('PR30', 'OP30', '终检包装', 30, TRUE)
ON CONFLICT DO NOTHING;

INSERT INTO demo.dim_line VALUES
    ('L01', 'LINE-01', '一号柔性产线', '精密制造一车间', 'running'),
    ('L02', 'LINE-02', '二号柔性产线', '精密制造一车间', 'running'),
    ('L03', 'LINE-03', '三号装配产线', '智能装配车间', 'running')
ON CONFLICT DO NOTHING;

INSERT INTO demo.dim_equipment
SELECT
    'E' || LPAD(gs::text, 2, '0'),
    'EQ-' || LPAD(gs::text, 3, '0'),
    CASE ((gs - 1) % 3) WHEN 0 THEN '数控加工中心' WHEN 1 THEN '热处理炉' ELSE '自动检测机' END || gs,
    CASE ((gs - 1) % 3) WHEN 0 THEN 'CNC' WHEN 1 THEN 'HEAT' ELSE 'INSPECTION' END,
    'L0' || (((gs - 1) / 3) + 1)::text,
    DATE '2021-01-01' + (gs * 45)
FROM generate_series(1, 9) AS gs
ON CONFLICT DO NOTHING;

WITH days AS (
    SELECT d::date AS business_date, ROW_NUMBER() OVER (ORDER BY d)::int AS day_no
    FROM generate_series(DATE '2025-10-01', DATE '2025-12-29', INTERVAL '1 day') d
), lines AS (
    SELECT line_id, ROW_NUMBER() OVER (ORDER BY line_id)::int AS line_no FROM demo.dim_line
)
INSERT INTO demo.fact_work_order
SELECT
    'WO-' || TO_CHAR(business_date, 'YYYYMMDD') || '-' || line_id,
    'MO' || TO_CHAR(business_date, 'YYMMDD') || line_no,
    business_date,
    'P0' || (((day_no + line_no) % 4) + 1)::text,
    line_id,
    760 + ((day_no * 17 + line_no * 41) % 260),
    CHR(64 + ((day_no + line_no) % 3) + 1),
    'completed'
FROM days CROSS JOIN lines
ON CONFLICT DO NOTHING;

WITH orders AS (
    SELECT w.*, ROW_NUMBER() OVER (ORDER BY plan_date, line_id)::bigint AS order_seq
    FROM demo.fact_work_order w
), processes AS (
    SELECT process_id, process_sequence, is_final_process,
           ROW_NUMBER() OVER (ORDER BY process_sequence)::bigint AS process_no
    FROM demo.dim_process
)
INSERT INTO demo.fact_process_output
SELECT
    order_seq * 10 + process_no,
    work_order_id,
    process_id,
    line_id,
    plan_date,
    GREATEST(planned_qty - process_no::int * 6 - ((order_seq + process_no * 7) % 23)::int
      - CASE WHEN line_id = 'L02' AND plan_date >= DATE '2025-12-16' THEN ((plan_date - DATE '2025-12-15') * 7) ELSE 0 END, 0),
    ((order_seq + process_no) % 8)::int,
    ((order_seq * process_no) % 5)::int,
    is_final_process
FROM orders CROSS JOIN processes
ON CONFLICT DO NOTHING;

WITH outputs AS (
    SELECT o.*, w.product_id, ROW_NUMBER() OVER (ORDER BY o.output_id)::bigint AS inspection_seq
    FROM demo.fact_process_output o
    JOIN demo.fact_work_order w USING (work_order_id)
), prepared AS (
    SELECT *, LEAST(completed_qty, 260 + (inspection_seq % 90)::int) AS inspected,
        CASE
          WHEN line_id = 'L02' AND output_date >= DATE '2025-12-16' THEN 16 + (inspection_seq % 11)::int
          WHEN process_id = 'PR20' THEN 7 + (inspection_seq % 8)::int
          ELSE 2 + (inspection_seq % 7)::int
        END AS defect_count
    FROM outputs
)
INSERT INTO demo.fact_quality_inspection
SELECT
    inspection_seq,
    work_order_id,
    product_id,
    process_id,
    output_date::timestamp + TIME '08:00' + ((inspection_seq % 10)::int * INTERVAL '45 minutes'),
    inspected,
    GREATEST(inspected - defect_count, 0),
    CASE WHEN defect_count::numeric / inspected > 0.07 THEN 'fail'
         WHEN defect_count::numeric / inspected > 0.035 THEN 'warning' ELSE 'pass' END,
    CASE (inspection_seq % 3) WHEN 0 THEN '质检一组' WHEN 1 THEN '质检二组' ELSE '质检三组' END
FROM prepared
WHERE inspected > 0
ON CONFLICT DO NOTHING;

INSERT INTO demo.fact_quality_defect
SELECT
    inspection_id,
    inspection_id,
    CASE (inspection_id % 5) WHEN 0 THEN '尺寸偏差' WHEN 1 THEN '表面划伤'
      WHEN 2 THEN '热处理硬度不足' WHEN 3 THEN '装配间隙' ELSE '外观污染' END,
    CASE WHEN inspected_qty - qualified_qty >= 20 THEN 'critical'
      WHEN inspected_qty - qualified_qty >= 10 THEN 'major' ELSE 'minor' END,
    inspected_qty - qualified_qty,
    CASE (inspection_id % 4) WHEN 0 THEN '设备' WHEN 1 THEN '工艺' WHEN 2 THEN '材料' ELSE '人员操作' END
FROM demo.fact_quality_inspection
WHERE inspected_qty > qualified_qty
ON CONFLICT DO NOTHING;

WITH days AS (
    SELECT d::date AS business_date, ROW_NUMBER() OVER (ORDER BY d)::bigint AS day_no
    FROM generate_series(DATE '2025-10-01', DATE '2025-12-29', INTERVAL '1 day') d
), equipment AS (
    SELECT equipment_id, ROW_NUMBER() OVER (ORDER BY equipment_id)::bigint AS eq_no
    FROM demo.dim_equipment
), events AS (
    SELECT *, 1 AS event_no FROM days CROSS JOIN equipment
    UNION ALL
    SELECT *, 2 AS event_no FROM days CROSS JOIN equipment WHERE (day_no + eq_no) % 3 = 0
)
INSERT INTO demo.fact_equipment_event
SELECT
    day_no * 1000 + eq_no * 10 + event_no,
    equipment_id,
    CASE WHEN event_no = 1 THEN 'downtime' ELSE 'alarm' END,
    CASE WHEN event_no = 1 THEN 'DT-' || ((day_no + eq_no) % 5)::text ELSE 'AL-' || ((day_no + eq_no) % 7)::text END,
    CASE ((day_no + eq_no) % 5) WHEN 0 THEN '换型调整' WHEN 1 THEN '温度偏高'
      WHEN 2 THEN '刀具更换' WHEN 3 THEN '传感器告警' ELSE '计划保养' END,
    business_date::timestamp + TIME '06:00' + ((eq_no * 53 + event_no * 97) % 900)::int * INTERVAL '1 minute',
    business_date::timestamp + TIME '06:00' + ((eq_no * 53 + event_no * 97) % 900)::int * INTERVAL '1 minute'
      + (CASE WHEN equipment_id = 'E08' AND business_date >= DATE '2025-12-10' THEN 145 ELSE 8 + ((day_no * eq_no + event_no) % 62) END) * INTERVAL '1 minute',
    CASE WHEN equipment_id = 'E08' AND business_date >= DATE '2025-12-10' THEN 145 ELSE 8 + ((day_no * eq_no + event_no) % 62) END,
    ((day_no + eq_no) % 7 = 0)
FROM events
ON CONFLICT DO NOTHING;

WITH days AS (
    SELECT d::date AS business_date, ROW_NUMBER() OVER (ORDER BY d)::bigint AS day_no
    FROM generate_series(DATE '2025-10-01', DATE '2025-12-29', INTERVAL '1 day') d
), shifts(shift_code, shift_no) AS (VALUES ('A', 1), ('B', 2), ('C', 3)),
lines AS (SELECT line_id, ROW_NUMBER() OVER (ORDER BY line_id)::bigint AS line_no FROM demo.dim_line)
INSERT INTO demo.fact_shift_summary
SELECT
    day_no * 100 + line_no * 10 + shift_no,
    business_date,
    shift_code,
    line_id,
    260 + ((day_no + line_no * 7 + shift_no * 11) % 70)::int,
    250 + ((day_no + line_no * 5 + shift_no * 13) % 65)::int,
    243 + ((day_no + line_no * 3 + shift_no * 17) % 60)::int
FROM days CROSS JOIN shifts CROSS JOIN lines
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS app.catalog_table (
    id BIGSERIAL PRIMARY KEY,
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    business_domain TEXT NOT NULL DEFAULT '通用',
    row_count BIGINT NOT NULL DEFAULT 0,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (schema_name, table_name)
);

CREATE TABLE IF NOT EXISTS app.catalog_column (
    id BIGSERIAL PRIMARY KEY,
    catalog_table_id BIGINT NOT NULL REFERENCES app.catalog_table(id) ON DELETE CASCADE,
    column_name TEXT NOT NULL,
    ordinal_position INTEGER NOT NULL,
    data_type TEXT NOT NULL,
    is_nullable BOOLEAN NOT NULL,
    is_primary_key BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT NOT NULL DEFAULT '',
    sample_values JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (catalog_table_id, column_name)
);

CREATE TABLE IF NOT EXISTS app.catalog_relation (
    id BIGSERIAL PRIMARY KEY,
    source_table_id BIGINT NOT NULL REFERENCES app.catalog_table(id) ON DELETE CASCADE,
    source_column TEXT NOT NULL,
    target_table_id BIGINT NOT NULL REFERENCES app.catalog_table(id) ON DELETE CASCADE,
    target_column TEXT NOT NULL,
    cardinality TEXT NOT NULL DEFAULT 'many-to-one',
    relation_type TEXT NOT NULL DEFAULT 'foreign_key',
    description TEXT NOT NULL DEFAULT '',
    UNIQUE (source_table_id, source_column, target_table_id, target_column)
);

CREATE TABLE IF NOT EXISTS app.business_topic (
    topic_code TEXT PRIMARY KEY,
    topic_name TEXT NOT NULL,
    description TEXT NOT NULL,
    accent_color TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.business_object (
    object_code TEXT PRIMARY KEY,
    topic_code TEXT NOT NULL REFERENCES app.business_topic(topic_code),
    object_name TEXT NOT NULL,
    description TEXT NOT NULL,
    mapped_tables JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.metric (
    metric_code TEXT PRIMARY KEY,
    topic_code TEXT NOT NULL REFERENCES app.business_topic(topic_code),
    metric_name TEXT NOT NULL,
    description TEXT NOT NULL,
    formula TEXT NOT NULL,
    unit TEXT NOT NULL,
    grain TEXT NOT NULL,
    dimensions JSONB NOT NULL DEFAULT '[]'::jsonb,
    mapped_tables JSONB NOT NULL DEFAULT '[]'::jsonb,
    owner_name TEXT NOT NULL DEFAULT '比赛项目组',
    version TEXT NOT NULL DEFAULT '1.0',
    status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('draft', 'published', 'disabled')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.business_rule (
    rule_code TEXT PRIMARY KEY,
    topic_code TEXT NOT NULL REFERENCES app.business_topic(topic_code),
    rule_name TEXT NOT NULL,
    rule_content TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'mandatory',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.synonym (
    id BIGSERIAL PRIMARY KEY,
    topic_code TEXT NOT NULL REFERENCES app.business_topic(topic_code),
    canonical_term TEXT NOT NULL,
    synonym_term TEXT NOT NULL,
    UNIQUE (topic_code, canonical_term, synonym_term)
);

INSERT INTO app.business_topic VALUES
    ('quality', '质量分析', '良率、不良率、缺陷 Pareto 与质量趋势', '#c8ff41', 1, NOW()),
    ('equipment', '设备异常', '停机、报警、设备健康与异常特征', '#ff6b2c', 2, NOW()),
    ('production', '生产趋势', '末工序产量、计划达成率与趋势变化', '#63d8ff', 3, NOW())
ON CONFLICT (topic_code) DO UPDATE SET topic_name = EXCLUDED.topic_name, description = EXCLUDED.description;

INSERT INTO app.business_object VALUES
    ('inspection', 'quality', '质量检验', '按产品、工序、工单发生的质量检验记录', '["demo.fact_quality_inspection", "demo.fact_quality_defect"]', NOW()),
    ('equipment_event', 'equipment', '设备事件', '设备停机与报警事件及持续时长', '["demo.fact_equipment_event", "demo.dim_equipment"]', NOW()),
    ('process_output', 'production', '生产产出', '工单在各工序的日汇总产出', '["demo.fact_process_output", "demo.fact_work_order"]', NOW())
ON CONFLICT (object_code) DO UPDATE SET description = EXCLUDED.description, mapped_tables = EXCLUDED.mapped_tables;

INSERT INTO app.metric VALUES
    ('yield_rate', 'quality', '良率', '检验合格数量占检验总数量的比例', 'SUM(qualified_qty) / NULLIF(SUM(inspected_qty), 0)', '%', '日期×产品×工序', '["日期", "产品", "工序", "产线"]', '["demo.fact_quality_inspection"]', '质量负责人', '1.0', 'published', NOW()),
    ('defect_rate', 'quality', '不良率', '检验不合格数量占检验总数量的比例', '1 - SUM(qualified_qty) / NULLIF(SUM(inspected_qty), 0)', '%', '日期×产品×工序', '["日期", "产品", "工序"]', '["demo.fact_quality_inspection"]', '质量负责人', '1.0', 'published', NOW()),
    ('downtime_minutes', 'equipment', '停机时长', '非计划停机事件持续分钟数之和', 'SUM(duration_minutes) FILTER (WHERE event_type = ''downtime'' AND is_planned = false)', '分钟', '日期×设备', '["日期", "设备", "产线", "原因"]', '["demo.fact_equipment_event"]', '设备负责人', '1.0', 'published', NOW()),
    ('final_output', 'production', '完工产量', '末工序完成数量之和，禁止跨工序累加', 'SUM(completed_qty) FILTER (WHERE is_final_process = true)', '件', '日期×产线', '["日期", "产线", "产品"]', '["demo.fact_process_output"]', '生产负责人', '1.0', 'published', NOW()),
    ('plan_attainment', 'production', '计划达成率', '同日期同产线末工序完工数量除以工单计划量', 'SUM(final_completed_qty) / NULLIF(SUM(planned_qty), 0)', '%', '日期×产线', '["日期", "产线"]', '["demo.fact_process_output", "demo.fact_work_order"]', '生产负责人', '1.0', 'published', NOW())
ON CONFLICT (metric_code) DO UPDATE SET description = EXCLUDED.description, formula = EXCLUDED.formula, mapped_tables = EXCLUDED.mapped_tables;

INSERT INTO app.business_rule VALUES
    ('quality-yield-source', 'quality', '良率唯一事实来源', '良率必须只从 fact_quality_inspection 的 qualified_qty / inspected_qty 计算，禁止连接缺陷明细后计算。', 'mandatory', NOW()),
    ('production-final-only', 'production', '产量只取末工序', '总产量和计划达成率只统计 is_final_process=true 的 completed_qty。', 'mandatory', NOW()),
    ('equipment-daily-feature', 'equipment', '设备特征先按日聚合', '设备异常建模前必须按设备和业务日聚合时长、次数、夜间比例等特征。', 'mandatory', NOW())
ON CONFLICT (rule_code) DO UPDATE SET rule_content = EXCLUDED.rule_content;

INSERT INTO app.synonym (topic_code, canonical_term, synonym_term) VALUES
    ('quality', '良率', '合格率'), ('quality', '不良率', '缺陷率'), ('quality', '缺陷', '不良项'),
    ('equipment', '停机时长', '宕机时间'), ('equipment', '设备事件', '设备报警'),
    ('production', '完工产量', '实际产量'), ('production', '计划达成率', '计划完成率')
ON CONFLICT DO NOTHING;

INSERT INTO app.app_config (config_key, config_value, updated_at) VALUES
    ('project_stage', '"phase-1"'::jsonb, NOW()),
    ('dataset_max_business_date', '"2025-12-29"'::jsonb, NOW())
ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value, updated_at = NOW();

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'demo_reader') THEN
        CREATE ROLE demo_reader NOLOGIN;
    END IF;
END $$;
GRANT USAGE ON SCHEMA demo TO demo_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA demo TO demo_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA demo GRANT SELECT ON TABLES TO demo_reader;
