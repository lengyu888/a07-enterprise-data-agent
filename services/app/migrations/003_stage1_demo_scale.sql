WITH outputs AS (
    SELECT o.*, w.product_id
    FROM demo.fact_process_output o
    JOIN demo.fact_work_order w USING (work_order_id)
), expanded AS (
    SELECT o.*, sample_no
    FROM outputs o
    CROSS JOIN generate_series(1, 70) AS sample_no
), prepared AS (
    SELECT *,
        45 + ((output_id + sample_no * 11) % 56)::int AS inspected,
        CASE
          WHEN line_id = 'L02' AND output_date >= DATE '2025-12-16'
            THEN 5 + ((output_id + sample_no) % 8)::int
          WHEN process_id = 'PR20'
            THEN 2 + ((output_id + sample_no * 3) % 5)::int
          ELSE 1 + ((output_id + sample_no * 7) % 4)::int
        END AS defect_count
    FROM expanded
)
INSERT INTO demo.fact_quality_inspection
SELECT
    output_id * 100 + sample_no,
    work_order_id,
    product_id,
    process_id,
    output_date::timestamp + TIME '06:00'
      + ((sample_no * 13 + output_id) % 960)::int * INTERVAL '1 minute',
    inspected,
    inspected - defect_count,
    CASE WHEN defect_count::numeric / inspected > 0.09 THEN 'fail'
         WHEN defect_count::numeric / inspected > 0.045 THEN 'warning' ELSE 'pass' END,
    CASE (sample_no % 3) WHEN 0 THEN '质检一组' WHEN 1 THEN '质检二组' ELSE '质检三组' END
FROM prepared
ON CONFLICT DO NOTHING;

INSERT INTO demo.fact_quality_defect
SELECT
    inspection_id,
    inspection_id,
    CASE (inspection_id % 10)
      WHEN 0 THEN '尺寸偏差' WHEN 1 THEN '尺寸偏差' WHEN 2 THEN '尺寸偏差'
      WHEN 3 THEN '表面划伤' WHEN 4 THEN '表面划伤'
      WHEN 5 THEN '热处理硬度不足' WHEN 6 THEN '热处理硬度不足'
      WHEN 7 THEN '装配间隙' WHEN 8 THEN '外观污染' ELSE '毛刺' END,
    CASE WHEN inspected_qty - qualified_qty >= 10 THEN 'critical'
      WHEN inspected_qty - qualified_qty >= 5 THEN 'major' ELSE 'minor' END,
    inspected_qty - qualified_qty,
    CASE (inspection_id % 4) WHEN 0 THEN '设备' WHEN 1 THEN '工艺'
      WHEN 2 THEN '材料' ELSE '人员操作' END
FROM demo.fact_quality_inspection
WHERE inspection_id > 1000 AND inspected_qty > qualified_qty
ON CONFLICT DO NOTHING;
