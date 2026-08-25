from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.catalog.service import refresh_catalog
from app.core.database import get_engine


router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


@router.get("/summary")
def catalog_summary() -> dict[str, object]:
    with get_engine().connect() as connection:
        summary = connection.execute(
            text(
                """
                SELECT COUNT(*) AS table_count,
                       COALESCE(SUM(row_count), 0) AS total_rows,
                       (SELECT COUNT(*) FROM app.catalog_column) AS column_count,
                       (SELECT COUNT(*) FROM app.catalog_relation) AS relation_count,
                       MAX(refreshed_at) AS refreshed_at
                FROM app.catalog_table
                """
            )
        ).mappings().one()
        max_date = connection.execute(
            text("SELECT config_value #>> '{}' FROM app.app_config WHERE config_key='dataset_max_business_date'")
        ).scalar_one_or_none()
    return {**summary, "dataset_max_business_date": max_date}


@router.get("/tables")
def list_tables(domain: str | None = None) -> list[dict[str, object]]:
    query = """
        SELECT t.id, t.schema_name, t.table_name, t.display_name, t.description,
               t.business_domain, t.row_count, t.refreshed_at,
               COUNT(c.id) AS column_count
        FROM app.catalog_table t
        LEFT JOIN app.catalog_column c ON c.catalog_table_id = t.id
    """
    params: dict[str, object] = {}
    if domain:
        query += " WHERE t.business_domain = :domain"
        params["domain"] = domain
    query += " GROUP BY t.id ORDER BY t.business_domain, t.table_name"
    with get_engine().connect() as connection:
        return [dict(row) for row in connection.execute(text(query), params).mappings()]


@router.get("/tables/{table_id}")
def table_detail(table_id: int) -> dict[str, object]:
    with get_engine().connect() as connection:
        table_row = connection.execute(
            text("SELECT * FROM app.catalog_table WHERE id=:table_id"), {"table_id": table_id}
        ).mappings().one_or_none()
        if table_row is None:
            raise HTTPException(status_code=404, detail="catalog table not found")
        columns = connection.execute(
            text(
                """
                SELECT id, column_name, ordinal_position, data_type, is_nullable,
                       is_primary_key, description, sample_values
                FROM app.catalog_column WHERE catalog_table_id=:table_id
                ORDER BY ordinal_position
                """
            ),
            {"table_id": table_id},
        ).mappings().all()
    return {**table_row, "columns": [dict(row) for row in columns]}


@router.get("/relations")
def list_relations() -> list[dict[str, object]]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT r.id, src.table_name AS source_table, r.source_column,
                       tgt.table_name AS target_table, r.target_column,
                       r.cardinality, r.relation_type, r.description
                FROM app.catalog_relation r
                JOIN app.catalog_table src ON src.id = r.source_table_id
                JOIN app.catalog_table tgt ON tgt.id = r.target_table_id
                ORDER BY src.table_name, r.source_column
                """
            )
        ).mappings().all()
    return [dict(row) for row in rows]


@router.post("/refresh")
def refresh() -> dict[str, object]:
    return {"status": "refreshed", **refresh_catalog()}
