from __future__ import annotations

import json
import operator
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from typing_extensions import TypedDict

from app.agent.analysis_graph import _trace
from app.core.config import Settings
from app.core.database import get_engine
from app.integrations.deepseek import DeepSeekGateway
from app.rag.retriever import retrieve_evidence


class QualityBriefContract(BaseModel):
    headline: str = Field(min_length=6, max_length=60)
    summary: str = Field(min_length=20, max_length=500)
    risks: list[str] = Field(min_length=2, max_length=4)
    actions: list[str] = Field(min_length=2, max_length=4)


class QualityBriefState(TypedDict, total=False):
    run_id: str
    evidence: list[dict[str, Any]]
    period_rows: list[dict[str, Any]]
    process_rows: list[dict[str, Any]]
    pareto_rows: list[dict[str, Any]]
    trend_rows: list[dict[str, Any]]
    assessment: dict[str, Any]
    brief: dict[str, Any]
    trace: Annotated[list[dict[str, Any]], operator.add]


def _value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _rows(result: Any) -> list[dict[str, Any]]:
    return [{key: _value(value) for key, value in dict(row).items()} for row in result.mappings().all()]


class QualityBriefGraph:
    """LangGraph workflow for a bounded, evidence-backed quality management brief."""

    def __init__(self, settings: Settings) -> None:
        self.gateway = DeepSeekGateway(settings)
        builder = StateGraph(QualityBriefState)
        builder.add_node("retrieve_quality_evidence", self.retrieve_quality_evidence)
        builder.add_node("aggregate_quality_kpis", self.aggregate_quality_kpis)
        builder.add_node("assess_quality_change", self.assess_quality_change)
        builder.add_node("compose_quality_brief", self.compose_quality_brief)
        builder.add_edge(START, "retrieve_quality_evidence")
        builder.add_edge("retrieve_quality_evidence", "aggregate_quality_kpis")
        builder.add_edge("aggregate_quality_kpis", "assess_quality_change")
        builder.add_edge("assess_quality_change", "compose_quality_brief")
        builder.add_edge("compose_quality_brief", END)
        self.graph = builder.compile()

    def invoke(self) -> QualityBriefState:
        return self.graph.invoke({"run_id": str(uuid4()), "trace": []})

    def retrieve_quality_evidence(self, _: QualityBriefState) -> dict[str, Any]:
        started = time.perf_counter()
        questions = ["分析本月各工序良率", "本月缺陷类型 Pareto 分析", "对比本月与上月总体良率"]
        bundles = [retrieve_evidence(question, top_k=8) for question in questions]
        evidence = [{
            "question": bundle["query"],
            "metric": bundle["metric"]["metric_name"],
            "metric_code": bundle["metric"]["metric_code"],
            "formula": bundle["metric"]["formula"],
            "tables": [table["table_name"] for table in bundle["tables"]],
            "top_sources": [item["title"] for item in bundle["items"][:3]],
        } for bundle in bundles]
        return {
            "evidence": evidence,
            "trace": _trace("retrieve_quality_evidence", "质量证据检索", started,
                            "为良率、缺陷 Pareto 与月度环比装配 3 组 EvidenceBundle",
                            {"metrics": [item["metric_code"] for item in evidence], "bundle_count": len(evidence)}),
        }

    def aggregate_quality_kpis(self, _: QualityBriefState) -> dict[str, Any]:
        started = time.perf_counter()
        period_sql = """
            WITH periods(period_key, period_label, start_date, end_date, sort_order) AS (
                VALUES ('previous', '2025-11', DATE '2025-11-01', DATE '2025-11-30', 1),
                       ('current', '2025-12', DATE '2025-12-01', DATE '2025-12-29', 2)
            )
            SELECT p.period_key, p.period_label,
                   ROUND(100.0 * SUM(q.qualified_qty) / NULLIF(SUM(q.inspected_qty), 0), 2) AS yield_rate,
                   SUM(q.inspected_qty) AS inspected_qty,
                   SUM(q.inspected_qty - q.qualified_qty) AS unqualified_qty
            FROM periods p
            JOIN demo.fact_quality_inspection q ON q.inspection_time::date BETWEEN p.start_date AND p.end_date
            GROUP BY p.period_key, p.period_label, p.sort_order ORDER BY p.sort_order
        """
        process_sql = """
            SELECT p.process_name,
                   ROUND(100.0 * SUM(q.qualified_qty) / NULLIF(SUM(q.inspected_qty), 0), 2) AS yield_rate,
                   SUM(q.inspected_qty) AS inspected_qty
            FROM demo.fact_quality_inspection q
            JOIN demo.dim_process p ON p.process_id=q.process_id
            WHERE q.inspection_time::date BETWEEN DATE '2025-12-01' AND DATE '2025-12-29'
            GROUP BY p.process_name ORDER BY yield_rate, p.process_name
        """
        pareto_sql = """
            WITH defect_summary AS (
                SELECT d.defect_type, SUM(d.defect_qty) AS defect_count
                FROM demo.fact_quality_defect d
                JOIN demo.fact_quality_inspection q ON q.inspection_id=d.inspection_id
                WHERE q.inspection_time::date BETWEEN DATE '2025-12-01' AND DATE '2025-12-29'
                GROUP BY d.defect_type
            )
            SELECT defect_type, defect_count,
                   ROUND(100.0 * defect_count / NULLIF(SUM(defect_count) OVER (), 0), 2) AS defect_share,
                   ROUND(100.0 * SUM(defect_count) OVER (ORDER BY defect_count DESC, defect_type)
                         / NULLIF(SUM(defect_count) OVER (), 0), 2) AS cumulative_share
            FROM defect_summary ORDER BY defect_count DESC, defect_type
        """
        trend_sql = """
            SELECT q.inspection_time::date AS business_date,
                   ROUND(100.0 * SUM(q.qualified_qty) / NULLIF(SUM(q.inspected_qty), 0), 2) AS yield_rate
            FROM demo.fact_quality_inspection q
            WHERE q.inspection_time::date BETWEEN DATE '2025-11-30' AND DATE '2025-12-29'
            GROUP BY q.inspection_time::date ORDER BY business_date
        """
        with get_engine().connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                for sql in (period_sql, process_sql, pareto_sql, trend_sql):
                    connection.execute(text(f"EXPLAIN (FORMAT JSON) {sql}"))
                period_rows = _rows(connection.execute(text(period_sql)))
                process_rows = _rows(connection.execute(text(process_sql)))
                pareto_rows = _rows(connection.execute(text(pareto_sql)))
                trend_rows = _rows(connection.execute(text(trend_sql)))
            finally:
                transaction.rollback()
        return {
            "period_rows": period_rows, "process_rows": process_rows,
            "pareto_rows": pareto_rows, "trend_rows": trend_rows,
            "trace": _trace("aggregate_quality_kpis", "质量指标聚合", started,
                            f"4 组只读查询返回 {len(period_rows) + len(process_rows) + len(pareto_rows) + len(trend_rows)} 行真实结果",
                            {"queries": 4, "read_only": True, "statement_timeout_ms": 5000}),
        }

    def assess_quality_change(self, state: QualityBriefState) -> dict[str, Any]:
        started = time.perf_counter()
        previous = next(row for row in state["period_rows"] if row["period_key"] == "previous")
        current = next(row for row in state["period_rows"] if row["period_key"] == "current")
        delta = round(float(current["yield_rate"]) - float(previous["yield_rate"]), 2)
        worst_process = state["process_rows"][0]
        top_defect = state["pareto_rows"][0]
        vital_few: list[str] = []
        for row in state["pareto_rows"]:
            vital_few.append(row["defect_type"])
            if float(row["cumulative_share"]) >= 80:
                break
        assessment = {
            "current_yield": current["yield_rate"], "previous_yield": previous["yield_rate"],
            "yield_delta_pp": delta, "inspected_qty": current["inspected_qty"],
            "unqualified_qty": current["unqualified_qty"],
            "worst_process": worst_process, "top_defect": top_defect,
            "vital_few": vital_few,
            "status": "attention" if delta < 0 else "stable",
        }
        return {
            "assessment": assessment,
            "trace": _trace("assess_quality_change", "质量变化诊断", started,
                            f"总体良率环比 {delta:+.2f} 个百分点；识别 {len(vital_few)} 类关键缺陷",
                            {"yield_delta_pp": delta, "worst_process": worst_process["process_name"], "vital_few": vital_few}),
        }

    def compose_quality_brief(self, state: QualityBriefState) -> dict[str, Any]:
        started = time.perf_counter()
        system_prompt = """你是制造业质量负责人 Agent。根据给定的确定性指标评估生成 JSON：
headline、summary、risks(2-4条)、actions(2-4条)。
必须写出良率及环比百分点、最低工序、关键缺陷；不得声称已找到根因；行动项只能建议核查或改进，不得编造数据。语言简练，适合管理层晨会。"""
        payload = {"period": {"start": "2025-12-01", "end": "2025-12-29", "previous": "2025-11"}, "assessment": state["assessment"]}
        try:
            brief = QualityBriefContract.model_validate(
                self.gateway.complete_json(system_prompt=system_prompt, user_prompt=json.dumps(payload, ensure_ascii=False, default=str))
            ).model_dump()
            mode = "deepseek"
        except (ValueError, ValidationError, json.JSONDecodeError):
            item = state["assessment"]
            brief = {
                "headline": "本月质量良率回落，关键缺陷需优先核查",
                "summary": f"2025-12-01 至 2025-12-29 总体良率为 {item['current_yield']}%，较上月变化 {item['yield_delta_pp']:+.2f} 个百分点。{item['worst_process']['process_name']}良率最低，缺陷重点集中在{'、'.join(item['vital_few'])}。",
                "risks": [f"{item['worst_process']['process_name']}良率为 {item['worst_process']['yield_rate']}%", f"{item['top_defect']['defect_type']}占缺陷数量 {item['top_defect']['defect_share']}%"],
                "actions": ["按工序与产品下钻核查低良率批次", "对关键缺陷关联设备、工艺和材料记录开展验证"],
            }
            mode = "guarded_fallback"
        brief["generation_mode"] = mode
        return {
            "brief": brief,
            "trace": _trace("compose_quality_brief", "DeepSeek 质量简报", started,
                            f"基于确定性评估生成管理层简报（{mode}）", {"mode": mode, "risk_count": len(brief["risks"])}),
        }


def build_quality_brief(settings: Settings) -> dict[str, Any]:
    started = time.perf_counter()
    state = QualityBriefGraph(settings).invoke()
    return {
        "run_id": state["run_id"], "status": "completed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": {"start": "2025-12-01", "end": "2025-12-29", "anchor": "2025-12-29", "previous_month": "2025-11"},
        "assessment": state["assessment"], "brief": state["brief"],
        "charts": {"process": state["process_rows"], "pareto": state["pareto_rows"], "trend": state["trend_rows"]},
        "evidence": state["evidence"], "trace": state["trace"],
        "duration_ms": max(1, round((time.perf_counter() - started) * 1000)),
    }
