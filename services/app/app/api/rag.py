from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import get_engine
from app.rag.indexer import refresh_index
from app.rag.retriever import retrieve_evidence


router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


class SearchRequest(BaseModel):
    question: str = Field(min_length=4, max_length=300)
    top_k: int = Field(default=10, ge=4, le=16)


@router.get("/status")
def status() -> dict[str, object]:
    with get_engine().connect() as connection:
        rows = connection.execute(text("""
            SELECT source_type, COUNT(*) AS count,
                   COUNT(embedding) AS embedded_count
            FROM app.knowledge_chunk GROUP BY source_type ORDER BY source_type
        """)).mappings().all()
    return {
        "status": "ready" if rows and all(row["count"] == row["embedded_count"] for row in rows) else "incomplete",
        "model": get_settings().embedding_model,
        "dimensions": 512,
        "index": [dict(row) for row in rows],
        "fusion": "RRF(exact, pg_trgm, pgvector)",
    }


@router.post("/search")
def search(payload: SearchRequest) -> dict[str, object]:
    try:
        return retrieve_evidence(payload.question, payload.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/reindex")
def reindex() -> dict[str, object]:
    return refresh_index()
