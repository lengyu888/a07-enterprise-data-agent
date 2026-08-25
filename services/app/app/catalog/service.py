from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.core.database import get_engine


TABLE_QUERY = text(
    """
    SELECT n.nspname AS schema_name,
           c.relname AS table_name,
           COALESCE(obj_description(c.oid, 'pg_class'), '') AS description
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'demo' AND c.relkind = 'r'
    ORDER BY c.relname
    """
)

COLUMN_QUERY = text(
    """
    SELECT n.nspname AS schema_name,
           c.relname AS table_name,
           a.attname AS column_name,
           a.attnum AS ordinal_position,
           format_type(a.atttypid, a.atttypmod) AS data_type,
           NOT a.attnotnull AS is_nullable,
           COALESCE(col_description(c.oid, a.attnum), '') AS description,
           EXISTS (
               SELECT 1 FROM pg_constraint pk
               WHERE pk.conrelid = c.oid AND pk.contype = 'p' AND a.attnum = ANY(pk.conkey)
           ) AS is_primary_key
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'demo' AND c.relkind = 'r'
      AND a.attnum > 0 AND NOT a.attisdropped
    ORDER BY c.relname, a.attnum
    """
)

RELATION_QUERY = text(
    """
    SELECT src_ns.nspname AS source_schema,
           src.relname AS source_table,
           src_col.attname AS source_column,
           tgt_ns.nspname AS target_schema,
           tgt.relname AS target_table,
           tgt_col.attname AS target_column
    FROM pg_constraint fk
    JOIN pg_class src ON src.oid = fk.conrelid
    JOIN pg_namespace src_ns ON src_ns.oid = src.relnamespace
    JOIN pg_class tgt ON tgt.oid = fk.confrelid
    JOIN pg_namespace tgt_ns ON tgt_ns.oid = tgt.relnamespace
    JOIN LATERAL unnest(fk.conkey, fk.confkey) AS keys(src_attnum, tgt_attnum) ON TRUE
    JOIN pg_attribute src_col ON src_col.attrelid = src.oid AND src_col.attnum = keys.src_attnum
    JOIN pg_attribute tgt_col ON tgt_col.attrelid = tgt.oid AND tgt_col.attnum = keys.tgt_attnum
    WHERE fk.contype = 'f' AND src_ns.nspname = 'demo' AND tgt_ns.nspname = 'demo'
    ORDER BY src.relname, src_col.attname
    """
)


def _domain(table_name: str) -> str:
    if "quality" in table_name:
        return "质量分析"
    if "equipment" in table_name:
        return "设备异常"
    if "work_order" in table_name or "output" in table_name or "shift" in table_name:
        return "生产趋势"
    return "基础主数据"


def _display_name(table_name: str) -> str:
    names = {
        "dim_product": "产品主数据",
        "dim_process": "工序主数据",
        "dim_line": "产线主数据",
        "dim_equipment": "设备主数据",
        "fact_work_order": "生产工单",
        "fact_process_output": "工序产量",
        "fact_quality_inspection": "质量检验",
        "fact_quality_defect": "质量缺陷",
        "fact_equipment_event": "设备事件",
        "fact_shift_summary": "班次汇总（留出）",
    }
    return names.get(table_name, table_name)


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, Decimal)):
        return str(value)
    return value


def refresh_catalog() -> dict[str, int]:
    engine = get_engine()
    with engine.begin() as connection:
        table_rows = connection.execute(TABLE_QUERY).mappings().all()
        column_rows = connection.execute(COLUMN_QUERY).mappings().all()
        relation_rows = connection.execute(RELATION_QUERY).mappings().all()
        quote = connection.dialect.identifier_preparer.quote

        table_ids: dict[tuple[str, str], int] = {}
        for row in table_rows:
            qualified_name = f"{quote(row['schema_name'])}.{quote(row['table_name'])}"
            row_count = connection.exec_driver_sql(
                f"SELECT COUNT(*) FROM {qualified_name}"
            ).scalar_one()
            table_id = connection.execute(
                text(
                    """
                    INSERT INTO app.catalog_table
                        (schema_name, table_name, display_name, description, business_domain, row_count, refreshed_at)
                    VALUES (:schema_name, :table_name, :display_name, :description, :business_domain, :row_count, NOW())
                    ON CONFLICT (schema_name, table_name) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        description = EXCLUDED.description,
                        business_domain = EXCLUDED.business_domain,
                        row_count = EXCLUDED.row_count,
                        refreshed_at = NOW()
                    RETURNING id
                    """
                ),
                {
                    **row,
                    "display_name": _display_name(row["table_name"]),
                    "business_domain": _domain(row["table_name"]),
                    "row_count": row_count,
                },
            ).scalar_one()
            table_ids[(row["schema_name"], row["table_name"])] = table_id

        active_names = [row["table_name"] for row in table_rows]
        connection.execute(
            text("DELETE FROM app.catalog_table WHERE schema_name = 'demo' AND NOT (table_name = ANY(:names))"),
            {"names": active_names},
        )
        if table_ids:
            connection.execute(
                text("DELETE FROM app.catalog_column WHERE catalog_table_id = ANY(:table_ids)"),
                {"table_ids": list(table_ids.values())},
            )

        for row in column_rows:
            table_id = table_ids[(row["schema_name"], row["table_name"])]
            qualified_name = f"{quote(row['schema_name'])}.{quote(row['table_name'])}"
            quoted_column = quote(row["column_name"])
            samples = connection.exec_driver_sql(
                f"SELECT DISTINCT {quoted_column} FROM {qualified_name} "
                f"WHERE {quoted_column} IS NOT NULL LIMIT 3"
            ).scalars().all()
            connection.execute(
                text(
                    """
                    INSERT INTO app.catalog_column
                        (catalog_table_id, column_name, ordinal_position, data_type, is_nullable,
                         is_primary_key, description, sample_values)
                    VALUES (:catalog_table_id, :column_name, :ordinal_position, :data_type,
                            :is_nullable, :is_primary_key, :description, CAST(:sample_values AS jsonb))
                    """
                ),
                {
                    **row,
                    "catalog_table_id": table_id,
                    "sample_values": __import__("json").dumps(
                        [_json_value(value) for value in samples], ensure_ascii=False
                    ),
                },
            )

        connection.execute(text("DELETE FROM app.catalog_relation"))
        for row in relation_rows:
            source_id = table_ids[(row["source_schema"], row["source_table"])]
            target_id = table_ids[(row["target_schema"], row["target_table"])]
            connection.execute(
                text(
                    """
                    INSERT INTO app.catalog_relation
                        (source_table_id, source_column, target_table_id, target_column,
                         cardinality, relation_type, description)
                    VALUES (:source_id, :source_column, :target_id, :target_column,
                            'many-to-one', 'foreign_key', :description)
                    """
                ),
                {
                    "source_id": source_id,
                    "source_column": row["source_column"],
                    "target_id": target_id,
                    "target_column": row["target_column"],
                    "description": f"{row['source_table']}.{row['source_column']} → {row['target_table']}.{row['target_column']}",
                },
            )

    return {
        "tables": len(table_rows),
        "columns": len(column_rows),
        "relations": len(relation_rows),
    }
