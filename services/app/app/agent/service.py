from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.agent.analysis_graph import HybridAnalysisGraph, SUPPORTED_QUESTIONS
from app.agent.quality_brief_graph import build_quality_brief
from app.core.config import get_settings
from app.core.database import get_engine


class AgentRunError(RuntimeError):
    def __init__(self, message: str, run_id: str, *, unsupported: bool = False) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.unsupported = unsupported


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def run_quality_analysis(question: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.deepseek_configured:
        raise AgentRunError("DeepSeek Secret 未配置，无法运行 Agent", "not-created")

    run_id = str(uuid4())
    started = time.perf_counter()
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO app.analysis_run (run_id, question, scene, status, model_id)
                VALUES (:run_id, :question, 'pending', 'running', :model_id)
                """
            ),
            {"run_id": run_id, "question": question, "model_id": settings.deepseek_model},
        )

    try:
        state = HybridAnalysisGraph(settings).invoke(question, run_id)
        duration_ms = max(1, round((time.perf_counter() - started) * 1000))
        with engine.begin() as connection:
            for index, step in enumerate(state["trace"], start=1):
                connection.execute(
                    text(
                        """
                        INSERT INTO app.run_step
                            (run_id, step_order, node_name, display_name, status, duration_ms, summary, payload)
                        VALUES (:run_id, :step_order, :node_name, :display_name, :status,
                                :duration_ms, :summary, CAST(:payload AS jsonb))
                        """
                    ),
                    {"run_id": run_id, "step_order": index, **step, "payload": _json(step.get("payload", {}))},
                )
            connection.execute(
                text(
                    """
                    INSERT INTO app.sql_artifact
                        (run_id, sql_text, validation_status, referenced_tables, executed_at, row_count)
                    VALUES (:run_id, :sql, 'passed', CAST(:tables AS jsonb), NOW(), :row_count)
                    """
                ),
                {"run_id": run_id, "sql": state["sql"], "tables": _json(state["referenced_tables"]), "row_count": len(state["rows"])},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO app.result_snapshot (run_id, columns, rows, chart_spec)
                    VALUES (:run_id, CAST(:columns AS jsonb), CAST(:rows AS jsonb), CAST(:chart AS jsonb))
                    """
                ),
                {"run_id": run_id, "columns": _json(state["columns"]), "rows": _json(state["rows"]), "chart": _json(state["chart_spec"])},
            )
            connection.execute(
                text(
                    """
                    UPDATE app.analysis_run SET status='completed', scene=:scene, answer=:answer,
                        generation_mode=:generation_mode, duration_ms=:duration_ms, completed_at=NOW()
                    WHERE run_id=:run_id
                    """
                ),
                {"run_id": run_id, "scene": state["scene"], "answer": state["answer"], "generation_mode": state["generation_mode"], "duration_ms": duration_ms},
            )
    except Exception as exc:
        duration_ms = max(1, round((time.perf_counter() - started) * 1000))
        message = str(exc)[:500]
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE app.analysis_run SET status='failed', error_message=:error,
                        duration_ms=:duration_ms, completed_at=NOW() WHERE run_id=:run_id
                    """
                ),
                {"run_id": run_id, "error": message, "duration_ms": duration_ms},
            )
        raise AgentRunError(message, run_id, unsupported="仅支持" in message) from exc

    return {
        "run_id": run_id,
        "status": "completed",
        "scene": state["scene"],
        "question": question,
        "model": settings.deepseek_model,
        "generation_mode": state["generation_mode"],
        "duration_ms": duration_ms,
        "time_range": state["time_range"],
        "plan": state["plan"],
        "evidence": {
            "metric": {"code": state["bundle"]["metric"]["metric_code"], "name": state["bundle"]["metric"]["metric_name"], "formula": state["bundle"]["metric"]["formula"], "version": state["bundle"]["metric"]["version"]},
            "rule": "；".join(item["rule_content"] for item in state["bundle"]["rules"]),
            "rules": state["bundle"]["rules"],
            "tables": [item["table_name"] for item in state["bundle"]["tables"]],
            "relations": state["bundle"]["relations"],
            "items": state["bundle"]["items"],
            "retrieval": state["bundle"]["retrieval"],
        },
        "sql": {"text": state["sql"], "validation": "passed", "repair_count": state.get("repair_count", 0), "referenced_tables": state["referenced_tables"]},
        "result": {"columns": state["columns"], "rows": state["rows"], "row_count": len(state["rows"])},
        "chart": state["chart_spec"],
        "answer": state["answer"],
        "trace": state["trace"],
    }


def list_recent_runs(limit: int = 10) -> list[dict[str, Any]]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT run_id, question, scene, status, model_id, generation_mode,
                       answer, error_message, started_at, completed_at, duration_ms
                FROM app.analysis_run ORDER BY started_at DESC LIMIT :limit
                """
            ),
            {"limit": min(max(limit, 1), 50)},
        ).mappings().all()
    return [dict(row) for row in rows]


def run_quality_brief() -> dict[str, Any]:
    settings = get_settings()
    if not settings.deepseek_configured:
        raise AgentRunError("DeepSeek Secret 未配置，无法生成质量简报", "not-created")
    try:
        return build_quality_brief(settings)
    except Exception as exc:
        raise AgentRunError(str(exc)[:500], "quality-brief") from exc


def capabilities() -> dict[str, Any]:
    return {
        "phase": "phase-4",
        "supported_scenes": ["quality", "equipment", "production"],
        "supported_questions": SUPPORTED_QUESTIONS,
        "pipeline": ["retrieve", "plan", "text_to_sql", "validate_sql", "repair_sql", "execute_sql", "build_chart", "summarize"],
        "limits": {"max_rows": 100, "statement_timeout_ms": 5000, "sql_mode": "read_only", "max_sql_repairs": 2},
        "rag": {"channels": ["exact", "pg_trgm", "pgvector"], "fusion": "RRF", "top_k": 10},
        "quality_specialization": ["process_yield", "defect_pareto", "daily_yield_trend", "month_over_month", "management_brief"],
    }


def stage3_evaluation_summary() -> dict[str, Any]:
    with get_engine().connect() as connection:
        completed = set(connection.execute(text(
            "SELECT DISTINCT question FROM app.analysis_run WHERE status='completed'"
        )).scalars().all())
    cases = [{"question": question, "completed": question in completed} for question in SUPPORTED_QUESTIONS]
    passed = sum(item["completed"] for item in cases)
    return {
        "total": len(cases), "completed": passed,
        "accuracy_pct": round(100 * passed / max(len(cases), 1), 1),
        "threshold_pct": 80, "passed": passed / max(len(cases), 1) >= 0.8,
        "cases": cases,
    }


def stage4_evaluation_summary() -> dict[str, Any]:
    quality_questions = [
        "本月缺陷类型 Pareto 分析",
        "最近30天每日良率趋势",
        "对比本月与上月总体良率",
    ]
    with get_engine().connect() as connection:
        rows = [dict(row) for row in connection.execute(text(
            """SELECT question, status, started_at FROM app.analysis_run
               WHERE scene='quality' OR question = ANY(:questions)
               ORDER BY started_at DESC LIMIT 20"""
        ), {"questions": quality_questions}).mappings()]
    consecutive = 0
    for row in rows:
        if row["status"] != "completed":
            break
        consecutive += 1
    covered = {row["question"] for row in rows if row["status"] == "completed"}
    cases = [{"question": question, "completed": question in covered} for question in quality_questions]
    return {
        "stage": "phase-4", "required_consecutive_successes": 3,
        "consecutive_successes": consecutive, "passed": consecutive >= 3 and all(item["completed"] for item in cases),
        "cases": cases,
    }
