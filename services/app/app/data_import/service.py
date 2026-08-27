from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.catalog.service import refresh_catalog
from app.core.database import get_engine


MAX_BYTES = 1_000_000
MAX_ROWS = 500
MIN_DATE = date(2025, 11, 1)
MAX_DATE = date(2025, 12, 29)
CHINA_TZ = timezone(timedelta(hours=8))

TEMPLATES: dict[str, dict[str, Any]] = {
    "quality_inspection": {
        "name": "质量检验记录",
        "scene": "质量分析",
        "description": "追加既有工单的工序检验数据，良率与结果等级由系统校验。",
        "target_tables": ["demo.fact_quality_inspection"],
        "columns": [
            "business_date", "order_no", "process_code", "inspected_qty",
            "qualified_qty", "inspector_group",
        ],
        "sample": ["2025-12-29", "MO2512291", "OP30", "120", "117", "QA-A"],
    },
    "equipment_event": {
        "name": "设备异常事件",
        "scene": "设备异常",
        "description": "追加停机或报警事件，持续时长由起止时间自动计算。",
        "target_tables": ["demo.fact_equipment_event"],
        "columns": [
            "equipment_code", "event_type", "event_code", "event_reason",
            "start_time", "end_time", "is_planned",
        ],
        "sample": [
            "EQ-001", "alarm", "ALM-901", "主轴温度偏高",
            "2025-12-29T09:10:00+08:00", "2025-12-29T09:22:00+08:00", "false",
        ],
    },
    "production_output": {
        "name": "生产完工记录",
        "scene": "生产趋势",
        "description": "创建新工单并写入末工序产出，用于产量与计划达成率分析。",
        "target_tables": ["demo.fact_work_order", "demo.fact_process_output"],
        "columns": [
            "business_date", "order_no", "product_code", "line_code", "planned_qty",
            "completed_qty", "scrap_qty", "rework_qty", "shift_code",
        ],
        "sample": ["2025-12-29", "IMP-20251229-01", "P-100", "LINE-01", "500", "482", "8", "4", "A"],
    },
}


class ImportValidationError(ValueError):
    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


def _sample_csv(template: dict[str, Any]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(template["columns"])
    writer.writerow(template["sample"])
    return output.getvalue()


def list_templates() -> list[dict[str, Any]]:
    return [
        {
            "code": code,
            **template,
            "sample_csv": _sample_csv(template),
            "limits": {"max_rows": MAX_ROWS, "date_range": [str(MIN_DATE), str(MAX_DATE)]},
        }
        for code, template in TEMPLATES.items()
    ]


def _read_rows(template_code: str, csv_text: str) -> list[dict[str, str]]:
    template = TEMPLATES.get(template_code)
    if template is None:
        raise ImportValidationError("不支持的数据模板")
    if not csv_text.strip():
        raise ImportValidationError("CSV 文件为空")
    if len(csv_text.encode("utf-8")) > MAX_BYTES:
        raise ImportValidationError("CSV 文件不能超过 1 MB")

    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")), strict=True)
    actual = reader.fieldnames or []
    expected = template["columns"]
    if actual != expected:
        raise ImportValidationError(
            "CSV 表头与模板不一致",
            [{"row": 1, "field": "header", "message": f"应为：{','.join(expected)}"}],
        )
    rows: list[dict[str, str]] = []
    try:
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ImportValidationError(
                    "CSV 数据列数超过模板",
                    [{"row": row_number, "field": "row", "message": "该行包含多余字段"}],
                )
            rows.append({key: (value or "").strip() for key, value in row.items()})
    except csv.Error as exc:
        raise ImportValidationError(f"CSV 格式错误：{exc}") from exc
    if not rows:
        raise ImportValidationError("CSV 至少需要一行数据")
    if len(rows) > MAX_ROWS:
        raise ImportValidationError(f"单次最多导入 {MAX_ROWS} 行")
    return rows


def _parse_date(value: str, row_number: int, errors: list[dict[str, Any]]) -> date | None:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        errors.append({"row": row_number, "field": "business_date", "message": "日期格式应为 YYYY-MM-DD"})
        return None
    if not MIN_DATE <= parsed <= MAX_DATE:
        errors.append({"row": row_number, "field": "business_date", "message": f"日期须在 {MIN_DATE} 至 {MAX_DATE}"})
        return None
    return parsed


def _parse_int(value: str, field: str, row_number: int, errors: list[dict[str, Any]], *, positive: bool = False) -> int | None:
    try:
        parsed = int(value)
    except ValueError:
        errors.append({"row": row_number, "field": field, "message": "须为整数"})
        return None
    if parsed < (1 if positive else 0):
        errors.append({"row": row_number, "field": field, "message": "数值超出允许范围"})
        return None
    return parsed


def _parse_datetime(value: str, field: str, row_number: int, errors: list[dict[str, Any]]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append({"row": row_number, "field": field, "message": "时间须为 ISO 8601 格式"})
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CHINA_TZ)
    local_date = parsed.astimezone(CHINA_TZ).date()
    if not MIN_DATE <= local_date <= MAX_DATE:
        errors.append({"row": row_number, "field": field, "message": f"业务时间须在 {MIN_DATE} 至 {MAX_DATE}"})
        return None
    return parsed


def _required(row: dict[str, str], row_number: int, errors: list[dict[str, Any]]) -> bool:
    missing = [field for field, value in row.items() if not value]
    errors.extend({"row": row_number, "field": field, "message": "不能为空"} for field in missing)
    return not missing


def _quality_records(connection: Any, rows: list[dict[str, str]], errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        if not _required(row, index, errors):
            continue
        business_date = _parse_date(row["business_date"], index, errors)
        inspected = _parse_int(row["inspected_qty"], "inspected_qty", index, errors, positive=True)
        qualified = _parse_int(row["qualified_qty"], "qualified_qty", index, errors)
        lookup = connection.execute(text("""
            SELECT w.work_order_id, w.product_id, w.plan_date, p.process_id
            FROM demo.fact_work_order w
            CROSS JOIN demo.dim_process p
            WHERE w.order_no=:order_no AND p.process_code=:process_code
        """), row).mappings().one_or_none()
        if lookup is None:
            errors.append({"row": index, "field": "order_no/process_code", "message": "工单或工序编码不存在"})
        if lookup and business_date and lookup["plan_date"] != business_date:
            errors.append({"row": index, "field": "business_date", "message": "检验日期必须与工单计划日期一致"})
        if inspected is not None and qualified is not None and qualified > inspected:
            errors.append({"row": index, "field": "qualified_qty", "message": "合格数不能大于检验数"})
        if not (business_date and lookup and lookup["plan_date"] == business_date and inspected is not None and qualified is not None and qualified <= inspected):
            continue
        yield_rate = qualified / inspected
        records.append({
            "work_order_id": lookup["work_order_id"], "product_id": lookup["product_id"], "process_id": lookup["process_id"],
            "inspection_time": datetime.combine(business_date, datetime.min.time(), CHINA_TZ) + timedelta(hours=12),
            "inspected_qty": inspected, "qualified_qty": qualified,
            "inspection_result": "pass" if yield_rate >= 0.98 else "warning" if yield_rate >= 0.95 else "fail",
            "inspector_group": row["inspector_group"],
        })
    return records


def _equipment_records(connection: Any, rows: list[dict[str, str]], errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        if not _required(row, index, errors):
            continue
        equipment_id = connection.execute(
            text("SELECT equipment_id FROM demo.dim_equipment WHERE equipment_code=:code"),
            {"code": row["equipment_code"]},
        ).scalar_one_or_none()
        if equipment_id is None:
            errors.append({"row": index, "field": "equipment_code", "message": "设备编码不存在"})
        if row["event_type"] not in {"downtime", "alarm"}:
            errors.append({"row": index, "field": "event_type", "message": "仅允许 downtime 或 alarm"})
        start = _parse_datetime(row["start_time"], "start_time", index, errors)
        end = _parse_datetime(row["end_time"], "end_time", index, errors)
        planned_map = {"true": True, "1": True, "是": True, "false": False, "0": False, "否": False}
        planned = planned_map.get(row["is_planned"].lower())
        if planned is None:
            errors.append({"row": index, "field": "is_planned", "message": "仅允许 true/false、1/0 或 是/否"})
        if start and end and end < start:
            errors.append({"row": index, "field": "end_time", "message": "结束时间不能早于开始时间"})
        if not (equipment_id and row["event_type"] in {"downtime", "alarm"} and start and end and end >= start and planned is not None):
            continue
        try:
            duration = Decimal(str((end - start).total_seconds() / 60)).quantize(Decimal("0.01"))
        except InvalidOperation:
            errors.append({"row": index, "field": "end_time", "message": "无法计算事件时长"})
            continue
        records.append({
            "equipment_id": equipment_id, "event_type": row["event_type"], "event_code": row["event_code"],
            "event_reason": row["event_reason"], "start_time": start, "end_time": end,
            "duration_minutes": duration, "is_planned": planned,
        })
    return records


def _production_records(connection: Any, rows: list[dict[str, str]], errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_orders: set[str] = set()
    final_process = connection.execute(text(
        "SELECT process_id FROM demo.dim_process WHERE is_final_process IS TRUE ORDER BY process_sequence DESC LIMIT 1"
    )).scalar_one()
    for index, row in enumerate(rows, start=2):
        if not _required(row, index, errors):
            continue
        business_date = _parse_date(row["business_date"], index, errors)
        quantities = {
            "planned_qty": _parse_int(row["planned_qty"], "planned_qty", index, errors, positive=True),
            "completed_qty": _parse_int(row["completed_qty"], "completed_qty", index, errors),
            "scrap_qty": _parse_int(row["scrap_qty"], "scrap_qty", index, errors),
            "rework_qty": _parse_int(row["rework_qty"], "rework_qty", index, errors),
        }
        master = connection.execute(text("""
            SELECT p.product_id, l.line_id
            FROM demo.dim_product p CROSS JOIN demo.dim_line l
            WHERE p.product_code=:product_code AND l.line_code=:line_code
        """), row).mappings().one_or_none()
        if master is None:
            errors.append({"row": index, "field": "product_code/line_code", "message": "产品或产线编码不存在"})
        exists = connection.execute(text(
            "SELECT 1 FROM demo.fact_work_order WHERE order_no=:order_no"
        ), row).scalar_one_or_none()
        if exists or row["order_no"] in seen_orders:
            errors.append({"row": index, "field": "order_no", "message": "工单号已存在或在文件内重复"})
        seen_orders.add(row["order_no"])
        if row["shift_code"] not in {"A", "B", "C"}:
            errors.append({"row": index, "field": "shift_code", "message": "仅允许 A、B、C"})
        if not (business_date and master and all(value is not None for value in quantities.values()) and row["shift_code"] in {"A", "B", "C"} and not exists):
            continue
        records.append({
            **dict(master), **quantities, "business_date": business_date, "order_no": row["order_no"],
            "shift_code": row["shift_code"], "process_id": final_process,
        })
    return records


def import_csv(template_code: str, source_filename: str, csv_text: str) -> dict[str, Any]:
    rows = _read_rows(template_code, csv_text)
    batch_id = str(uuid4())
    errors: list[dict[str, Any]] = []
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(7007)"))
        if template_code == "quality_inspection":
            records = _quality_records(connection, rows, errors)
        elif template_code == "equipment_event":
            records = _equipment_records(connection, rows, errors)
        else:
            records = _production_records(connection, rows, errors)
        if errors:
            raise ImportValidationError(f"发现 {len(errors)} 个数据问题，未写入任何记录", errors[:50])

        if template_code == "quality_inspection":
            next_id = connection.execute(text("SELECT COALESCE(MAX(inspection_id), 0) FROM demo.fact_quality_inspection")).scalar_one()
            connection.execute(text("""
                INSERT INTO demo.fact_quality_inspection
                    (inspection_id, work_order_id, product_id, process_id, inspection_time,
                     inspected_qty, qualified_qty, inspection_result, inspector_group)
                VALUES (:inspection_id, :work_order_id, :product_id, :process_id, :inspection_time,
                        :inspected_qty, :qualified_qty, :inspection_result, :inspector_group)
            """), [{**record, "inspection_id": next_id + index} for index, record in enumerate(records, start=1)])
        elif template_code == "equipment_event":
            next_id = connection.execute(text("SELECT COALESCE(MAX(event_id), 0) FROM demo.fact_equipment_event")).scalar_one()
            connection.execute(text("""
                INSERT INTO demo.fact_equipment_event
                    (event_id, equipment_id, event_type, event_code, event_reason, start_time,
                     end_time, duration_minutes, is_planned)
                VALUES (:event_id, :equipment_id, :event_type, :event_code, :event_reason, :start_time,
                        :end_time, :duration_minutes, :is_planned)
            """), [{**record, "event_id": next_id + index} for index, record in enumerate(records, start=1)])
        else:
            next_output = connection.execute(text("SELECT COALESCE(MAX(output_id), 0) FROM demo.fact_process_output")).scalar_one()
            prepared = [
                {**record, "work_order_id": f"IMP-{batch_id[:8]}-{index:03d}", "output_id": next_output + index}
                for index, record in enumerate(records, start=1)
            ]
            connection.execute(text("""
                INSERT INTO demo.fact_work_order
                    (work_order_id, order_no, plan_date, product_id, line_id, planned_qty, shift_code, order_status)
                VALUES (:work_order_id, :order_no, :business_date, :product_id, :line_id, :planned_qty, :shift_code, 'completed')
            """), prepared)
            connection.execute(text("""
                INSERT INTO demo.fact_process_output
                    (output_id, work_order_id, process_id, line_id, output_date, completed_qty,
                     scrap_qty, rework_qty, is_final_process)
                VALUES (:output_id, :work_order_id, :process_id, :line_id, :business_date, :completed_qty,
                        :scrap_qty, :rework_qty, TRUE)
            """), prepared)

        template = TEMPLATES[template_code]
        summary = {"accepted_rows": len(records), "rejected_rows": 0, "date_range": [str(MIN_DATE), str(MAX_DATE)]}
        connection.execute(text("""
            INSERT INTO app.data_import_batch
                (batch_id, template_code, source_filename, target_tables, row_count, status, summary)
            VALUES (CAST(:batch_id AS uuid), :template_code, :source_filename,
                    CAST(:target_tables AS jsonb), :row_count, 'completed', CAST(:summary AS jsonb))
        """), {
            "batch_id": batch_id, "template_code": template_code,
            "source_filename": source_filename[:255] or "import.csv",
            "target_tables": json.dumps(template["target_tables"]), "row_count": len(records),
            "summary": json.dumps(summary),
        })
    refresh_catalog()
    return {
        "batch_id": batch_id, "status": "completed", "template_code": template_code,
        "template_name": TEMPLATES[template_code]["name"], "row_count": len(records),
        "target_tables": TEMPLATES[template_code]["target_tables"], "summary": summary,
    }


def recent_imports(limit: int = 10) -> list[dict[str, Any]]:
    with get_engine().connect() as connection:
        rows = connection.execute(text("""
            SELECT batch_id, template_code, source_filename, target_tables, row_count,
                   status, summary, created_at
            FROM app.data_import_batch ORDER BY created_at DESC LIMIT :limit
        """), {"limit": min(max(limit, 1), 30)}).mappings().all()
    return [dict(row) for row in rows]
