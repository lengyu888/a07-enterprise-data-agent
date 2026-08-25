from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.agent.quality_graph import QualityThinSliceGraph, SUPPORTED_QUESTION
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
                VALUES (:run_id, :question, 'quality', 'running', :model_id)
                """
            ),
            {"run_id": run_id, "question": question, "model_id": settings.deepseek_model},
        )

    try:
        state = QualityThinSliceGraph(settings).invoke(question, run_id)
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
                    UPDATE app.analysis_run SET status='completed', answer=:answer,
                        generation_mode=:generation_mode, duration_ms=:duration_ms, completed_at=NOW()
                    WHERE run_id=:run_id
                    """
                ),
                {"run_id": run_id, "answer": state["answer"], "generation_mode": state["generation_mode"], "duration_ms": duration_ms},
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
            "metric": {"name": state["metric"]["metric_name"], "formula": state["metric"]["formula"], "version": state["metric"]["version"]},
            "rule": state["rule"]["rule_content"],
            "tables": [f"demo.{item['table_name']}" for item in state["tables"]],
            "relations": state["relations"],
        },
        "sql": {"text": state["sql"], "validation": "passed", "referenced_tables": state["referenced_tables"]},
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


def capabilities() -> dict[str, Any]:
    return {
        "phase": "phase-2",
        "supported_scenes": ["quality"],
        "supported_questions": [SUPPORTED_QUESTION],
        "pipeline": ["understand", "retrieve", "plan", "text_to_sql", "validate_sql", "execute_sql", "build_chart", "summarize"],
        "limits": {"max_rows": 100, "statement_timeout_ms": 5000, "sql_mode": "read_only"},
    }
