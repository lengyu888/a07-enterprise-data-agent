from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.agent.analysis_graph import HybridAnalysisGraph, SUPPORTED_QUESTIONS
from app.agent.algorithm_suite import ALGORITHM_ORDER, evaluate_algorithm_suite, list_algorithm_recipes
from app.agent.clarification_graph import ClarificationGraph, UnsafeQuestionError
from app.agent.conversation import contextualize_follow_up, suggestions_for_scene
from app.agent.equipment_anomaly_graph import EquipmentAnomalyGraph
from app.agent.production_trend_graph import ProductionTrendGraph
from app.agent.quality_brief_graph import build_quality_brief
from app.agent.run_control import RunCancelledError, clear_cancellation, ensure_not_cancelled, request_cancellation
from app.core.config import get_settings
from app.core.database import get_engine


class AgentRunError(RuntimeError):
    def __init__(self, message: str, run_id: str, *, unsupported: bool = False, cancelled: bool = False) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.unsupported = unsupported
        self.cancelled = cancelled


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def run_quality_analysis(
    question: str,
    clarification_id: str | None = None,
    *,
    request_id: str | None = None,
    parent_run_id: str | None = None,
    retry_of_run_id: str | None = None,
) -> dict[str, Any]:
    engine = get_engine()
    original_question = question.strip()
    resolved_question = original_question
    context_trace: list[dict[str, Any]] = []
    follow_up_suggestions: list[str] = []

    if parent_run_id:
        with engine.connect() as connection:
            parent = connection.execute(text("""
                SELECT run_id, question, scene, answer
                FROM app.analysis_run
                WHERE run_id=:run_id AND status='completed'
            """), {"run_id": parent_run_id}).mappings().one_or_none()
        if parent is None:
            raise AgentRunError("上一轮问析不存在或尚未完成，无法继续追问", "not-created", unsupported=True)
        contextualized = contextualize_follow_up(
            original_question,
            parent_question=parent["question"],
            parent_scene=parent["scene"],
            parent_answer=parent["answer"],
        )
        resolved_question = contextualized["resolved_question"]
        context_trace = contextualized["trace"]
        follow_up_suggestions = contextualized["suggestions"]

    try:
        preflight = ClarificationGraph().invoke(resolved_question)
    except UnsafeQuestionError as exc:
        raise AgentRunError(str(exc), "not-created", unsupported=True) from exc

    if preflight["status"] == "needs_clarification":
        new_clarification_id = str(uuid4())
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO app.clarification_event
                    (clarification_id, original_question, detected_scene, missing_fields, options)
                VALUES (:clarification_id, :question, :scene, CAST(:missing_fields AS jsonb), CAST(:options AS jsonb))
            """), {
                "clarification_id": new_clarification_id, "question": question,
                "scene": preflight.get("detected_scene"),
                "missing_fields": _json(preflight["missing_fields"]), "options": _json(preflight["options"]),
            })
        return {
            "status": "needs_clarification", "clarification_id": new_clarification_id,
            "question": original_question, "resolved_question": resolved_question,
            "parent_run_id": parent_run_id, "detected_scene": preflight.get("detected_scene"),
            "missing_fields": preflight["missing_fields"], "prompt": preflight["prompt"],
            "options": preflight["options"], "trace": context_trace + preflight["trace"],
        }

    if clarification_id:
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE app.clarification_event
                SET resolved_question=:question, resolved_at=NOW()
                WHERE clarification_id=CAST(:clarification_id AS uuid) AND resolved_at IS NULL
            """), {"question": resolved_question, "clarification_id": clarification_id})

    settings = get_settings()
    if not settings.deepseek_configured:
        raise AgentRunError("DeepSeek 尚未配置，请先进入模型配置页面填写 API Key", "not-created")

    run_id = request_id or str(uuid4())
    if retry_of_run_id:
        with engine.connect() as connection:
            retry_exists = connection.execute(
                text("SELECT 1 FROM app.analysis_run WHERE run_id=:run_id"),
                {"run_id": retry_of_run_id},
            ).scalar_one_or_none()
        if retry_exists is None:
            retry_of_run_id = None
    started = time.perf_counter()
    try:
        ensure_not_cancelled(run_id)
    except RunCancelledError as exc:
        clear_cancellation(run_id)
        raise AgentRunError(str(exc), run_id, cancelled=True) from exc
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO app.analysis_run
                    (run_id, question, original_question, parent_run_id, retry_of_run_id, scene, status, model_id)
                VALUES (:run_id, :question, :original_question, :parent_run_id, :retry_of_run_id,
                        'pending', 'running', :model_id)
                """
            ),
            {
                "run_id": run_id, "question": resolved_question, "original_question": original_question,
                "parent_run_id": parent_run_id, "retry_of_run_id": retry_of_run_id,
                "model_id": settings.deepseek_model,
            },
        )

    try:
        state = HybridAnalysisGraph(settings).invoke(resolved_question, run_id)
        ensure_not_cancelled(run_id)
        state["trace"] = context_trace + preflight["trace"] + state["trace"]
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
                        (run_id, sql_text, validation_status, referenced_tables, executed_at, row_count, repair_count)
                    VALUES (:run_id, :sql, 'passed', CAST(:tables AS jsonb), NOW(), :row_count, :repair_count)
                    """
                ),
                {"run_id": run_id, "sql": state["sql"], "tables": _json(state["referenced_tables"]), "row_count": len(state["rows"]), "repair_count": state.get("repair_count", 0)},
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
    except RunCancelledError as exc:
        duration_ms = max(1, round((time.perf_counter() - started) * 1000))
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE app.analysis_run
                SET status='cancelled', error_message=:error, cancel_requested_at=COALESCE(cancel_requested_at, NOW()),
                    duration_ms=:duration_ms, completed_at=NOW()
                WHERE run_id=:run_id AND status='running'
            """), {"run_id": run_id, "error": str(exc), "duration_ms": duration_ms})
        raise AgentRunError(str(exc), run_id, cancelled=True) from exc
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
    finally:
        clear_cancellation(run_id)

    return {
        "run_id": run_id,
        "status": "completed",
        "scene": state["scene"],
        "question": resolved_question,
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
        "conversation": {
            "original_question": original_question,
            "resolved_question": resolved_question,
            "parent_run_id": parent_run_id,
            "retry_of_run_id": retry_of_run_id,
            "suggestions": follow_up_suggestions or suggestions_for_scene(state["scene"]),
        },
    }


def cancel_analysis_run(run_id: str) -> dict[str, Any]:
    request_cancellation(run_id)
    with get_engine().begin() as connection:
        row = connection.execute(text("""
            UPDATE app.analysis_run
            SET status='cancelled', cancel_requested_at=NOW(), completed_at=NOW(),
                error_message='本次 Agent 运行已由用户取消'
            WHERE run_id=:run_id AND status='running'
            RETURNING run_id, status, cancel_requested_at
        """), {"run_id": run_id}).mappings().one_or_none()
        if row is None:
            current = connection.execute(text(
                "SELECT run_id, status, cancel_requested_at FROM app.analysis_run WHERE run_id=:run_id"
            ), {"run_id": run_id}).mappings().one_or_none()
    if row:
        return {**dict(row), "accepted": True}
    if current:
        clear_cancellation(run_id)
        return {**dict(current), "accepted": False}
    return {"run_id": run_id, "status": "cancellation_requested", "cancel_requested_at": None, "accepted": True}


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


def run_equipment_diagnosis() -> dict[str, Any]:
    settings = get_settings()
    if not settings.deepseek_configured:
        raise AgentRunError("DeepSeek Secret 未配置，无法生成设备诊断", "not-created")
    run_id = str(uuid4())
    started = time.perf_counter()
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO app.algorithm_run (run_id, recipe_code, scene, status, model_version)
            VALUES (:run_id, 'equipment-daily-iforest-v1', 'equipment', 'running', '1.0')
        """), {"run_id": run_id})
    try:
        state = EquipmentAnomalyGraph(settings).invoke(run_id)
        duration_ms = max(1, round((time.perf_counter() - started) * 1000))
        anomaly_rows = sum(row["is_anomaly"] for row in state["scored_rows"])
        top_name = state["assessment"]["top_equipment"]["equipment_name"]
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE app.algorithm_run SET status='completed', input_rows=:input_rows,
                    anomaly_rows=:anomaly_rows, top_entity=:top_entity, duration_ms=:duration_ms,
                    completed_at=NOW() WHERE run_id=:run_id
            """), {"run_id": run_id, "input_rows": len(state["baseline_rows"]) + len(state["scored_rows"]),
                     "anomaly_rows": anomaly_rows, "top_entity": top_name, "duration_ms": duration_ms})
    except Exception as exc:
        duration_ms = max(1, round((time.perf_counter() - started) * 1000))
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE app.algorithm_run SET status='failed', error_message=:error,
                    duration_ms=:duration_ms, completed_at=NOW() WHERE run_id=:run_id
            """), {"run_id": run_id, "error": str(exc)[:500], "duration_ms": duration_ms})
        raise AgentRunError(str(exc)[:500], run_id) from exc
    return {
        "run_id": run_id, "status": "completed", "duration_ms": duration_ms,
        "period": {"training": state["recipe"]["training_window"], "scoring": state["recipe"]["scoring_window"], "anchor": "2025-12-29"},
        "recipe": {
            "code": state["recipe"]["recipe_code"], "name": state["recipe"]["recipe_name"],
            "algorithm": state["recipe"]["algorithm_name"], "version": state["recipe"]["version"],
            "features": state["recipe"]["feature_columns"], "parameters": state["recipe"]["parameters"],
            "feature_sql": state["recipe"]["feature_sql"], "explanation_rule": state["recipe"]["explanation_rule"],
        },
        "assessment": state["assessment"], "ranking": state["ranking"],
        "timeline": state["timeline"], "deviations": state["deviations"],
        "reason_distribution": state["reason_distribution"], "brief": state["brief"],
        "evidence": state["evidence"], "trace": state["trace"],
    }


def run_production_trend() -> dict[str, Any]:
    settings = get_settings()
    if not settings.deepseek_configured:
        raise AgentRunError("DeepSeek Secret 未配置，无法生成生产趋势简报", "not-created")
    run_id = str(uuid4())
    started = time.perf_counter()
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO app.algorithm_run (run_id, recipe_code, scene, status, model_version)
            VALUES (:run_id, 'production-7d-linear-trend-v1', 'production', 'running', '1.0')
        """), {"run_id": run_id})
    try:
        state = ProductionTrendGraph(settings).invoke(run_id)
        duration_ms = max(1, round((time.perf_counter() - started) * 1000))
        attention_line = state["assessment"]["attention_line"]["line_name"]
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE app.algorithm_run SET status='completed', input_rows=:input_rows,
                    anomaly_rows=0, top_entity=:top_entity, duration_ms=:duration_ms,
                    completed_at=NOW() WHERE run_id=:run_id
            """), {"run_id": run_id, "input_rows": len(state["feature_rows"]),
                     "top_entity": attention_line, "duration_ms": duration_ms})
    except Exception as exc:
        duration_ms = max(1, round((time.perf_counter() - started) * 1000))
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE app.algorithm_run SET status='failed', error_message=:error,
                    duration_ms=:duration_ms, completed_at=NOW() WHERE run_id=:run_id
            """), {"run_id": run_id, "error": str(exc)[:500], "duration_ms": duration_ms})
        raise AgentRunError(str(exc)[:500], run_id) from exc
    return {
        "run_id": run_id, "status": "completed", "duration_ms": duration_ms,
        "period": {"start": "2025-12-01", "end": "2025-12-29", "anchor": "2025-12-29", "trend_window": "2025-12-23..2025-12-29"},
        "recipe": {
            "code": state["recipe"]["recipe_code"], "name": state["recipe"]["recipe_name"],
            "algorithm": state["recipe"]["algorithm_name"], "version": state["recipe"]["version"],
            "features": state["recipe"]["feature_columns"], "parameters": state["recipe"]["parameters"],
            "feature_sql": state["recipe"]["feature_sql"], "explanation_rule": state["recipe"]["explanation_rule"],
        },
        "assessment": state["assessment"], "ranking": state["monthly_rows"],
        "daily_trend": state["daily_total"], "line_trends": state["line_trends"],
        "brief": state["brief"], "evidence": state["evidence"], "trace": state["trace"],
    }


def algorithm_recipes() -> dict[str, Any]:
    return list_algorithm_recipes()


def run_algorithm_evaluation() -> dict[str, Any]:
    try:
        return evaluate_algorithm_suite()
    except Exception as exc:
        raise AgentRunError(str(exc)[:500], "algorithm-suite") from exc


def capabilities() -> dict[str, Any]:
    return {
        "phase": "phase-7",
        "supported_scenes": ["quality", "equipment", "production"],
        "supported_questions": SUPPORTED_QUESTIONS,
        "pipeline": ["contextualize", "clarify", "retrieve", "plan", "text_to_sql", "validate_sql", "repair_sql", "execute_sql", "build_chart", "summarize"],
        "interaction": {"multi_turn": True, "cancellable": True, "retryable": True},
        "data_import": {"templates": ["quality_inspection", "equipment_event", "production_output"], "max_rows": 500},
        "limits": {"max_rows": 100, "statement_timeout_ms": 5000, "sql_mode": "read_only", "max_sql_repairs": 2},
        "rag": {"channels": ["exact", "pg_trgm", "pgvector"], "fusion": "RRF", "top_k": 10},
        "quality_specialization": ["process_yield", "defect_pareto", "daily_yield_trend", "month_over_month", "management_brief"],
        "equipment_specialization": ["daily_feature_recipe", "isolation_forest", "anomaly_ranking", "robust_deviation", "diagnosis_brief"],
        "production_specialization": ["final_process_output", "plan_attainment", "seven_day_slope", "production_brief"],
        "algorithm_recipes": ALGORITHM_ORDER,
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


def stage5_evaluation_summary() -> dict[str, Any]:
    with get_engine().connect() as connection:
        rows = [dict(row) for row in connection.execute(text("""
            SELECT run_id, status, input_rows, anomaly_rows, top_entity, duration_ms, started_at
            FROM app.algorithm_run WHERE recipe_code='equipment-daily-iforest-v1'
            ORDER BY started_at DESC LIMIT 10
        """)).mappings()]
    consecutive = 0
    for row in rows:
        if row["status"] != "completed":
            break
        consecutive += 1
    return {
        "stage": "phase-5", "required_consecutive_successes": 3,
        "consecutive_successes": consecutive, "passed": consecutive >= 3,
        "latest_runs": rows[:3],
    }


def stage6_evaluation_summary() -> dict[str, Any]:
    with get_engine().connect() as connection:
        production_runs = [dict(row) for row in connection.execute(text("""
            SELECT run_id, status, input_rows, top_entity, duration_ms, started_at
            FROM app.algorithm_run WHERE recipe_code='production-7d-linear-trend-v1'
            ORDER BY started_at DESC LIMIT 10
        """)).mappings()]
        suite = connection.execute(text("""
            SELECT run_id, status, algorithm_count, duration_ms, completed_at
            FROM app.algorithm_evaluation_run ORDER BY started_at DESC LIMIT 1
        """)).mappings().one_or_none()
    consecutive = 0
    for row in production_runs:
        if row["status"] != "completed":
            break
        consecutive += 1
    suite_row = dict(suite) if suite else None
    return {
        "stage": "phase-6", "required_consecutive_successes": 3,
        "consecutive_successes": consecutive,
        "algorithm_suite": suite_row,
        "passed": consecutive >= 3 and bool(suite_row and suite_row["status"] == "completed" and suite_row["algorithm_count"] == 6),
        "latest_runs": production_runs[:3],
    }
