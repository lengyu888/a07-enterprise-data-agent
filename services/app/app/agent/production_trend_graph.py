from __future__ import annotations

import json
import operator
import time
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

import numpy as np
import sqlglot
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, ValidationError
from sklearn.linear_model import LinearRegression
from sqlalchemy import text
from sqlglot import exp
from typing_extensions import TypedDict

from app.agent.analysis_graph import _trace
from app.core.config import Settings
from app.core.database import get_engine
from app.integrations.deepseek import DeepSeekGateway
from app.rag.retriever import retrieve_evidence


ALLOWED_PRODUCTION_TABLES = {
    "demo.fact_process_output",
    "demo.fact_work_order",
    "demo.dim_line",
}


class ProductionBriefContract(BaseModel):
    headline: str = Field(min_length=6, max_length=80)
    summary: str = Field(min_length=20, max_length=600)
    observations: list[str] = Field(min_length=2, max_length=4)
    actions: list[str] = Field(min_length=2, max_length=4)


class ProductionState(TypedDict, total=False):
    run_id: str
    recipe: dict[str, Any]
    evidence: dict[str, Any]
    feature_rows: list[dict[str, Any]]
    monthly_rows: list[dict[str, Any]]
    daily_total: list[dict[str, Any]]
    line_trends: list[dict[str, Any]]
    assessment: dict[str, Any]
    brief: dict[str, Any]
    trace: Annotated[list[dict[str, Any]], operator.add]


def _value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _safe_feature_sql(sql: str) -> tuple[str, list[str]]:
    statements = sqlglot.parse(sql, read="postgres")
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValueError("生产 Recipe 只允许单条 SELECT/CTE")
    tree = statements[0]
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command)
    if any(tree.find(kind) is not None for kind in forbidden):
        raise ValueError("生产 Recipe 包含禁止的 DDL/DML")
    cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    tables = sorted({
        f"{table.db}.{table.name}" if table.db else table.name
        for table in tree.find_all(exp.Table)
        if table.name and table.name not in cte_names
    })
    if not set(tables).issubset(ALLOWED_PRODUCTION_TABLES):
        raise ValueError(f"生产 Recipe 引用了未审核表：{tables}")
    return tree.sql(dialect="postgres", pretty=True), tables


class ProductionTrendGraph:
    """Bounded production analysis: RAG -> reviewed SQL -> slope -> assessment -> brief."""

    def __init__(self, settings: Settings) -> None:
        self.gateway = DeepSeekGateway(settings)
        builder = StateGraph(ProductionState)
        builder.add_node("load_recipe", self.load_recipe)
        builder.add_node("execute_text_to_sql", self.execute_text_to_sql)
        builder.add_node("fit_seven_day_trend", self.fit_seven_day_trend)
        builder.add_node("assess_plan_attainment", self.assess_plan_attainment)
        builder.add_node("compose_production_brief", self.compose_production_brief)
        builder.add_edge(START, "load_recipe")
        builder.add_edge("load_recipe", "execute_text_to_sql")
        builder.add_edge("execute_text_to_sql", "fit_seven_day_trend")
        builder.add_edge("fit_seven_day_trend", "assess_plan_attainment")
        builder.add_edge("assess_plan_attainment", "compose_production_brief")
        builder.add_edge("compose_production_brief", END)
        self.graph = builder.compile()

    def invoke(self, run_id: str) -> ProductionState:
        return self.graph.invoke({"run_id": run_id, "trace": []})

    def load_recipe(self, _: ProductionState) -> dict[str, Any]:
        started = time.perf_counter()
        with get_engine().connect() as connection:
            recipe = dict(connection.execute(text(
                "SELECT * FROM app.analysis_recipe "
                "WHERE recipe_code='production-7d-linear-trend-v1' AND status='published'"
            )).mappings().one())
        safe_sql, tables = _safe_feature_sql(recipe["feature_sql"])
        bundles = [
            retrieve_evidence("本月各产线完工产量排名", top_k=8),
            retrieve_evidence("本月各产线计划达成率", top_k=8),
        ]
        recipe["feature_sql"] = safe_sql
        evidence = {
            "metrics": [{
                "code": bundle["metric"]["metric_code"],
                "name": bundle["metric"]["metric_name"],
                "formula": bundle["metric"]["formula"],
                "version": bundle["metric"]["version"],
            } for bundle in bundles],
            "tables": tables,
            "rules": sorted({rule["rule_content"] for bundle in bundles for rule in bundle["rules"]}),
            "sources": [item["title"] for bundle in bundles for item in bundle["items"][:3]],
            "retrieval": [bundle["retrieval"] for bundle in bundles],
        }
        return {
            "recipe": recipe,
            "evidence": evidence,
            "trace": _trace(
                "load_recipe", "RAG 与生产 Recipe", started,
                "检索完工产量、计划达成率口径并锁定审核 SQL",
                {"recipe_code": recipe["recipe_code"], "metric_count": 2, "tables": tables},
            ),
        }

    def execute_text_to_sql(self, state: ProductionState) -> dict[str, Any]:
        started = time.perf_counter()
        sql = state["recipe"]["feature_sql"]
        with get_engine().connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                connection.execute(text(f"EXPLAIN (FORMAT JSON) {sql}"))
                rows = [
                    {key: _value(value) for key, value in dict(row).items()}
                    for row in connection.execute(text(sql)).mappings().all()
                ]
            finally:
                transaction.rollback()
        if len(rows) < 21:
            raise ValueError("生产趋势样本不足，至少需要 7 日 × 3 条产线")
        return {
            "feature_rows": rows,
            "trace": _trace(
                "execute_text_to_sql", "Text-to-SQL 安全执行", started,
                f"SQLGlot 白名单、EXPLAIN 与只读事务通过，返回 {len(rows)} 个产线日",
                {"row_count": len(rows), "read_only": True, "statement_timeout_ms": 5000},
            ),
        }

    def fit_seven_day_trend(self, state: ProductionState) -> dict[str, Any]:
        started = time.perf_counter()
        current = [row for row in state["feature_rows"] if "2025-12-01" <= row["business_date"] <= "2025-12-29"]
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in current:
            grouped[row["line_id"]].append(row)
        line_trends: list[dict[str, Any]] = []
        for line_rows in grouped.values():
            line_rows.sort(key=lambda item: item["business_date"])
            window = line_rows[-int(state["recipe"]["parameters"]["fit_days"]):]
            x = np.arange(len(window), dtype=float).reshape(-1, 1)
            y = np.asarray([float(row["final_output"]) for row in window], dtype=float)
            model = LinearRegression().fit(x, y)
            slope = round(float(model.coef_[0]), 2)
            line_trends.append({
                "line_id": window[0]["line_id"],
                "line_name": window[0]["line_name"],
                "window_start": window[0]["business_date"],
                "window_end": window[-1]["business_date"],
                "slope_per_day": slope,
                "direction": "上升" if slope > 1 else "下降" if slope < -1 else "平稳",
                "start_output": window[0]["final_output"],
                "end_output": window[-1]["final_output"],
                "series": [{"business_date": row["business_date"], "final_output": row["final_output"]} for row in window],
            })
        line_trends.sort(key=lambda item: (-item["slope_per_day"], item["line_id"]))
        return {
            "line_trends": line_trends,
            "trace": _trace(
                "fit_seven_day_trend", "七日线性趋势", started,
                f"对 {len(line_trends)} 条产线分别拟合最近 7 日斜率，不外推未来产量",
                {"algorithm": "LinearRegression", "fit_days": 7, "mode": "trend_calculation"},
            ),
        }

    def assess_plan_attainment(self, state: ProductionState) -> dict[str, Any]:
        started = time.perf_counter()
        current = [row for row in state["feature_rows"] if "2025-12-01" <= row["business_date"] <= "2025-12-29"]
        by_line: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in current:
            by_line[row["line_id"]].append(row)
            by_date[row["business_date"]].append(row)
        trend_lookup = {item["line_id"]: item for item in state["line_trends"]}
        ranking = []
        for line_id, rows in by_line.items():
            actual = int(sum(int(row["final_output"]) for row in rows))
            planned = int(sum(int(row["planned_qty"]) for row in rows))
            ranking.append({
                "line_id": line_id,
                "line_name": rows[0]["line_name"],
                "final_output": actual,
                "planned_qty": planned,
                "plan_attainment": round(100 * actual / planned, 2),
                "slope_per_day": trend_lookup[line_id]["slope_per_day"],
                "direction": trend_lookup[line_id]["direction"],
            })
        ranking.sort(key=lambda item: (-item["plan_attainment"], item["line_id"]))
        daily_total = []
        for business_date in sorted(by_date):
            rows = by_date[business_date]
            actual = int(sum(int(row["final_output"]) for row in rows))
            planned = int(sum(int(row["planned_qty"]) for row in rows))
            daily_total.append({
                "business_date": business_date,
                "final_output": actual,
                "planned_qty": planned,
                "plan_attainment": round(100 * actual / planned, 2),
            })
        overall_actual = sum(item["final_output"] for item in ranking)
        overall_planned = sum(item["planned_qty"] for item in ranking)
        assessment = {
            "final_output": overall_actual,
            "planned_qty": overall_planned,
            "plan_attainment": round(100 * overall_actual / overall_planned, 2),
            "best_line": ranking[0],
            "attention_line": ranking[-1],
            "rising_lines": sum(item["direction"] == "上升" for item in ranking),
            "declining_lines": sum(item["direction"] == "下降" for item in ranking),
            "status": "attention" if ranking[-1]["plan_attainment"] < 95 else "stable",
            "trend_disclaimer": "七日斜率仅描述短期方向，不是未来产量预测。",
        }
        return {
            "monthly_rows": ranking,
            "daily_total": daily_total,
            "assessment": assessment,
            "trace": _trace(
                "assess_plan_attainment", "生产达成评估", started,
                f"末工序完工 {overall_actual} 件，整体计划达成率 {assessment['plan_attainment']}%",
                {"best_line": ranking[0]["line_id"], "attention_line": ranking[-1]["line_id"]},
            ),
        }

    def compose_production_brief(self, state: ProductionState) -> dict[str, Any]:
        started = time.perf_counter()
        system_prompt = """你是制造业生产运营 Agent。根据确定性生产指标输出 JSON：headline、summary、observations(2-4条)、actions(2-4条)。
必须写出整体完工量、计划达成率、最低达成产线和七日斜率；只能把斜率称为短期趋势，不得称为预测，不得编造停机或质量根因。"""
        payload = {
            "period": "2025-12-01..2025-12-29",
            "assessment": state["assessment"],
            "line_ranking": state["monthly_rows"],
        }
        try:
            generated = self.gateway.complete_json(
                system_prompt=system_prompt,
                user_prompt=json.dumps(payload, ensure_ascii=False, default=str),
            )
            normalized = {
                "headline": str(generated.get("headline", ""))[:80],
                "summary": str(generated.get("summary", ""))[:600],
                "observations": [str(item)[:240] for item in generated.get("observations", [])[:4]],
                "actions": [str(item)[:240] for item in generated.get("actions", [])[:4]],
            }
            brief = ProductionBriefContract.model_validate(normalized).model_dump()
            mode = "deepseek"
        except (ValueError, ValidationError, json.JSONDecodeError):
            item = state["assessment"]
            weak = item["attention_line"]
            brief = {
                "headline": "整体生产达成稳定，二号线需优先关注",
                "summary": f"本月末工序完工 {item['final_output']} 件，整体计划达成率 {item['plan_attainment']}%。{weak['line_name']}达成率最低，为 {weak['plan_attainment']}%，最近七日斜率为 {weak['slope_per_day']:+.2f} 件/日。",
                "observations": [f"{item['best_line']['line_name']}达成率最高，为 {item['best_line']['plan_attainment']}%", f"{weak['line_name']}与其他产线存在达成差距"],
                "actions": ["按日期下钻二号线计划与实际差异", "结合设备、质量记录核查差距，但不直接推断原因"],
            }
            mode = "guarded_fallback"
        brief["generation_mode"] = mode
        return {
            "brief": brief,
            "trace": _trace(
                "compose_production_brief", "DeepSeek 生产简报", started,
                f"在趋势非预测约束下生成生产运营简报（{mode}）",
                {"mode": mode, "observation_count": len(brief["observations"])},
            ),
        }
