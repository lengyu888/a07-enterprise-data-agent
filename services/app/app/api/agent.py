from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent.service import (
    AgentRunError,
    algorithm_recipes,
    capabilities,
    list_recent_runs,
    run_algorithm_evaluation,
    run_equipment_diagnosis,
    run_quality_analysis,
    run_quality_brief,
    run_production_trend,
    stage3_evaluation_summary,
    stage4_evaluation_summary,
    stage5_evaluation_summary,
    stage6_evaluation_summary,
)


router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class AgentQuestion(BaseModel):
    question: str = Field(min_length=4, max_length=300)


def _agent_error_status(exc: AgentRunError) -> int:
    if exc.run_id == "not-created":
        return 412
    if exc.unsupported:
        return 422
    return 502


@router.get("/capabilities")
def get_capabilities() -> dict[str, object]:
    return capabilities()


@router.get("/runs")
def recent_runs(limit: int = Query(default=10, ge=1, le=50)) -> list[dict[str, object]]:
    return list_recent_runs(limit)


@router.get("/evaluation/stage3")
def stage3_evaluation() -> dict[str, object]:
    return stage3_evaluation_summary()


@router.get("/evaluation/stage4")
def stage4_evaluation() -> dict[str, object]:
    return stage4_evaluation_summary()


@router.post("/quality/brief")
def create_quality_brief() -> dict[str, object]:
    try:
        return run_quality_brief()
    except AgentRunError as exc:
        raise HTTPException(status_code=_agent_error_status(exc), detail={"message": str(exc), "run_id": exc.run_id}) from exc


@router.post("/equipment/diagnosis")
def create_equipment_diagnosis() -> dict[str, object]:
    try:
        return run_equipment_diagnosis()
    except AgentRunError as exc:
        raise HTTPException(status_code=_agent_error_status(exc), detail={"message": str(exc), "run_id": exc.run_id}) from exc


@router.get("/evaluation/stage5")
def stage5_evaluation() -> dict[str, object]:
    return stage5_evaluation_summary()


@router.post("/production/trend")
def create_production_trend() -> dict[str, object]:
    try:
        return run_production_trend()
    except AgentRunError as exc:
        raise HTTPException(status_code=_agent_error_status(exc), detail={"message": str(exc), "run_id": exc.run_id}) from exc


@router.get("/algorithms")
def get_algorithm_recipes() -> dict[str, object]:
    return algorithm_recipes()


@router.post("/algorithms/evaluate")
def evaluate_algorithms() -> dict[str, object]:
    try:
        return run_algorithm_evaluation()
    except AgentRunError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc), "run_id": exc.run_id}) from exc


@router.get("/evaluation/stage6")
def stage6_evaluation() -> dict[str, object]:
    return stage6_evaluation_summary()


@router.post("/runs")
def create_run(payload: AgentQuestion) -> dict[str, object]:
    try:
        return run_quality_analysis(payload.question)
    except AgentRunError as exc:
        raise HTTPException(
            status_code=_agent_error_status(exc),
            detail={"message": str(exc), "run_id": exc.run_id},
        ) from exc
