from __future__ import annotations

import math
from typing import Any

from sqlalchemy import text

from app.agent.analysis_graph import SUPPORTED_QUESTIONS
from app.core.database import get_engine
from app.rag.retriever import retrieve_evidence


def _percent(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def _rag_benchmark() -> dict[str, Any]:
    with get_engine().connect() as connection:
        cases = [dict(row) for row in connection.execute(text("""
            SELECT case_code, scene, question, metric_code, expected_tables
            FROM app.validation_case ORDER BY scene, case_code
        """)).mappings()]

    results: list[dict[str, Any]] = []
    expected_table_count = 0
    recalled_table_count = 0
    metric_hits = 0
    for case in cases:
        expected_tables = list(case["expected_tables"])
        expected_table_count += len(expected_tables)
        try:
            bundle = retrieve_evidence(case["question"], top_k=10)
            actual_tables = [item["table_name"] for item in bundle["tables"]]
            recalled = [table for table in expected_tables if table in actual_tables]
            metric_ok = bundle["metric"]["metric_code"] == case["metric_code"]
            recalled_table_count += len(recalled)
            metric_hits += int(metric_ok)
            passed = metric_ok and len(recalled) == len(expected_tables)
            results.append({
                "case_code": case["case_code"], "scene": case["scene"], "question": case["question"],
                "metric_ok": metric_ok, "expected_tables": expected_tables,
                "recalled_tables": recalled, "passed": passed,
            })
        except Exception as exc:
            results.append({
                "case_code": case["case_code"], "scene": case["scene"], "question": case["question"],
                "metric_ok": False, "expected_tables": expected_tables,
                "recalled_tables": [], "passed": False, "error": type(exc).__name__,
            })

    passed_cases = sum(item["passed"] for item in results)
    return {
        "case_count": len(results),
        "passed_cases": passed_cases,
        "case_pass_pct": _percent(passed_cases, len(results)),
        "required_table_recall_pct": _percent(recalled_table_count, expected_table_count),
        "metric_accuracy_pct": _percent(metric_hits, len(results)),
        "top_k": 10,
        "cases": results,
    }


def evaluation_overview() -> dict[str, Any]:
    engine = get_engine()
    with engine.connect() as connection:
        run_rows = [dict(row) for row in connection.execute(text("""
            SELECT r.run_id, r.question, r.scene, r.status, r.model_id, r.generation_mode,
                   r.duration_ms, r.started_at, COALESCE(a.repair_count, 0) AS repair_count,
                   (r.answer IS NOT NULL
                    AND EXISTS (SELECT 1 FROM app.run_step s WHERE s.run_id=r.run_id AND s.node_name='retrieve' AND s.status='completed')
                    AND EXISTS (SELECT 1 FROM app.sql_artifact x WHERE x.run_id=r.run_id)
                    AND EXISTS (SELECT 1 FROM app.result_snapshot p WHERE p.run_id=r.run_id)) AS evidence_complete
            FROM app.analysis_run r
            LEFT JOIN app.sql_artifact a ON a.run_id=r.run_id
            ORDER BY r.started_at DESC LIMIT 50
        """)).mappings()]
        clarification = dict(connection.execute(text("""
            SELECT COUNT(*)::int AS total,
                   COUNT(*) FILTER (WHERE resolved_at IS NOT NULL)::int AS resolved,
                   COUNT(*) FILTER (WHERE resolved_at IS NULL)::int AS pending
            FROM app.clarification_event
        """)).mappings().one())
        generated_at = connection.execute(text("SELECT NOW()" )).scalar_one()

    total = len(run_rows)
    completed_rows = [row for row in run_rows if row["status"] == "completed"]
    completed = len(completed_rows)
    failed = sum(row["status"] == "failed" for row in run_rows)
    durations = sorted(int(row["duration_ms"] or 0) for row in completed_rows)
    p95_duration = durations[min(len(durations) - 1, max(0, math.ceil(len(durations) * 0.95) - 1))] if durations else 0
    one_pass = sum(int(row["repair_count"] or 0) == 0 for row in completed_rows)
    evidence_complete = sum(bool(row["evidence_complete"]) for row in completed_rows)
    completed_questions = {row["question"] for row in completed_rows}
    covered_questions = sum(question in completed_questions for question in SUPPORTED_QUESTIONS)
    rag = _rag_benchmark()

    metric_values = [
        ("rag_recall", "RAG 必需表召回", rag["required_table_recall_pct"], "%", 95.0, "gte", "验证案例中应出现的数据表是否进入 EvidenceBundle"),
        ("sql_first_pass", "SQL 一次通过", _percent(one_pass, completed), "%", 80.0, "gte", "无需修复即可通过 SQLGlot 并执行的问析占比"),
        ("run_success", "问析成功率", _percent(completed, total), "%", 90.0, "gte", "最近 50 次通用问析中完成执行的比例"),
        ("evidence_chain", "证据链完整率", _percent(evidence_complete, completed), "%", 100.0, "gte", "同时具备 RAG、SQL、结果快照和结论的成功运行"),
        ("question_coverage", "标准问题覆盖", _percent(covered_questions, len(SUPPORTED_QUESTIONS)), "%", 80.0, "gte", "20 个标准问题中已有成功运行记录的比例"),
        ("p95_latency", "P95 问析延迟", float(p95_duration), "ms", 120000.0, "lte", "最近成功运行的第 95 百分位端到端耗时"),
    ]
    metrics = [{
        "key": key, "label": label, "value": value, "unit": unit,
        "threshold": threshold, "direction": direction,
        "passed": value >= threshold if direction == "gte" else bool(value and value <= threshold),
        "description": description,
    } for key, label, value, unit, threshold, direction, description in metric_values]
    passed_gates = sum(metric["passed"] for metric in metrics)
    clarification["resolution_pct"] = _percent(clarification["resolved"], clarification["total"])

    return {
        "generated_at": generated_at,
        "window": {"runs": total, "limit": 50, "completed": completed, "failed": failed},
        "summary": {
            "passed_gates": passed_gates, "total_gates": len(metrics),
            "status": "ready" if passed_gates >= 5 else "attention" if passed_gates >= 3 else "insufficient_data",
        },
        "metrics": metrics,
        "rag": rag,
        "clarification": clarification,
        "recent_runs": run_rows[:10],
        "methodology": "固定验证案例 + 最近 50 次真实运行；不调用 DeepSeek 生成评测分数。",
    }
