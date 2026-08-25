from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent.service import AgentRunError, capabilities, list_recent_runs, run_quality_analysis, stage3_evaluation_summary


router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class AgentQuestion(BaseModel):
    question: str = Field(min_length=4, max_length=300)


@router.get("/capabilities")
def get_capabilities() -> dict[str, object]:
    return capabilities()


@router.get("/runs")
def recent_runs(limit: int = Query(default=10, ge=1, le=50)) -> list[dict[str, object]]:
    return list_recent_runs(limit)


@router.get("/evaluation/stage3")
def stage3_evaluation() -> dict[str, object]:
    return stage3_evaluation_summary()


@router.post("/runs")
def create_run(payload: AgentQuestion) -> dict[str, object]:
    try:
        return run_quality_analysis(payload.question)
    except AgentRunError as exc:
        raise HTTPException(
            status_code=422 if exc.unsupported else 502,
            detail={"message": str(exc), "run_id": exc.run_id},
        ) from exc
