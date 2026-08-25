from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.database import get_engine
from app.rag.indexer import refresh_index


router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class MetricInput(BaseModel):
    metric_code: str = Field(pattern=r"^[a-z][a-z0-9_]{2,48}$")
    topic_code: Literal["quality", "equipment", "production"]
    metric_name: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=4, max_length=500)
    formula: str = Field(min_length=3, max_length=1000)
    unit: str = Field(min_length=1, max_length=20)
    grain: str = Field(min_length=2, max_length=100)
    dimensions: list[str] = Field(default_factory=list)
    mapped_tables: list[str] = Field(default_factory=list)
    owner_name: str = "比赛项目组"
    version: str = "1.0"
    status: Literal["draft", "published", "disabled"] = "draft"


@router.get("/overview")
def knowledge_overview() -> dict[str, object]:
    engine = get_engine()
    with engine.connect() as connection:
        topics = connection.execute(
            text(
                """
                SELECT t.topic_code, t.topic_name, t.description, t.accent_color,
                       COUNT(DISTINCT m.metric_code) AS metric_count,
                       COUNT(DISTINCT r.rule_code) AS rule_count,
                       COUNT(DISTINCT o.object_code) AS object_count
                FROM app.business_topic t
                LEFT JOIN app.metric m ON m.topic_code=t.topic_code
                LEFT JOIN app.business_rule r ON r.topic_code=t.topic_code
                LEFT JOIN app.business_object o ON o.topic_code=t.topic_code
                GROUP BY t.topic_code ORDER BY t.sort_order
                """
            )
        ).mappings().all()
        rules = connection.execute(
            text("SELECT * FROM app.business_rule ORDER BY topic_code, rule_code")
        ).mappings().all()
        synonyms = connection.execute(
            text("SELECT topic_code, canonical_term, synonym_term FROM app.synonym ORDER BY topic_code, canonical_term")
        ).mappings().all()
    return {
        "topics": [dict(row) for row in topics],
        "rules": [dict(row) for row in rules],
        "synonyms": [dict(row) for row in synonyms],
    }


@router.get("/metrics")
def list_metrics(topic: str | None = None) -> list[dict[str, object]]:
    query = "SELECT * FROM app.metric"
    params: dict[str, object] = {}
    if topic:
        query += " WHERE topic_code=:topic"
        params["topic"] = topic
    query += " ORDER BY topic_code, metric_code"
    with get_engine().connect() as connection:
        return [dict(row) for row in connection.execute(text(query), params).mappings()]


@router.post("/metrics", status_code=status.HTTP_201_CREATED)
def create_metric(payload: MetricInput) -> dict[str, object]:
    with get_engine().begin() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM app.metric WHERE metric_code=:metric_code"),
            {"metric_code": payload.metric_code},
        ).scalar_one_or_none()
        if exists:
            raise HTTPException(status_code=409, detail="metric code already exists")
        connection.execute(
            text(
                """
                INSERT INTO app.metric
                    (metric_code, topic_code, metric_name, description, formula, unit, grain,
                     dimensions, mapped_tables, owner_name, version, status)
                VALUES (:metric_code, :topic_code, :metric_name, :description, :formula, :unit, :grain,
                        CAST(:dimensions AS jsonb), CAST(:mapped_tables AS jsonb), :owner_name, :version, :status)
                """
            ),
            {**payload.model_dump(exclude={"dimensions", "mapped_tables"}),
             "dimensions": __import__("json").dumps(payload.dimensions, ensure_ascii=False),
             "mapped_tables": __import__("json").dumps(payload.mapped_tables, ensure_ascii=False)},
        )
    index_result = refresh_index()
    return {"status": "created", "metric_code": payload.metric_code, "rag_embedded": index_result["embedded"]}


@router.put("/metrics/{metric_code}")
def update_metric(metric_code: str, payload: MetricInput) -> dict[str, object]:
    if metric_code != payload.metric_code:
        raise HTTPException(status_code=422, detail="metric code in path and body must match")
    with get_engine().begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE app.metric SET topic_code=:topic_code, metric_name=:metric_name,
                    description=:description, formula=:formula, unit=:unit, grain=:grain,
                    dimensions=CAST(:dimensions AS jsonb), mapped_tables=CAST(:mapped_tables AS jsonb),
                    owner_name=:owner_name, version=:version, status=:status, updated_at=NOW()
                WHERE metric_code=:metric_code
                """
            ),
            {**payload.model_dump(exclude={"dimensions", "mapped_tables"}),
             "dimensions": __import__("json").dumps(payload.dimensions, ensure_ascii=False),
             "mapped_tables": __import__("json").dumps(payload.mapped_tables, ensure_ascii=False)},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="metric not found")
    index_result = refresh_index()
    return {"status": "updated", "metric_code": metric_code, "rag_embedded": index_result["embedded"]}


@router.delete("/metrics/{metric_code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_metric(metric_code: str) -> Response:
    with get_engine().begin() as connection:
        result = connection.execute(
            text("DELETE FROM app.metric WHERE metric_code=:metric_code"), {"metric_code": metric_code}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="metric not found")
    refresh_index()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
