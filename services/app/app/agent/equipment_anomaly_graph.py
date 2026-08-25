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
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text
from sqlglot import exp
from typing_extensions import TypedDict

from app.agent.analysis_graph import _trace
from app.core.config import Settings
from app.core.database import get_engine
from app.integrations.deepseek import DeepSeekGateway
from app.rag.retriever import retrieve_evidence


ALLOWED_FEATURE_TABLES = {"demo.fact_equipment_event", "demo.dim_equipment", "demo.dim_line"}


class EquipmentBriefContract(BaseModel):
    headline: str = Field(min_length=6, max_length=80)
    summary: str = Field(min_length=20, max_length=600)
    risks: list[str] = Field(min_length=2, max_length=4)
    actions: list[str] = Field(min_length=2, max_length=4)


class EquipmentState(TypedDict, total=False):
    run_id: str
    recipe: dict[str, Any]
    evidence: dict[str, Any]
    feature_rows: list[dict[str, Any]]
    baseline_rows: list[dict[str, Any]]
    scored_rows: list[dict[str, Any]]
    ranking: list[dict[str, Any]]
    assessment: dict[str, Any]
    timeline: list[dict[str, Any]]
    reason_distribution: list[dict[str, Any]]
    deviations: list[dict[str, Any]]
    brief: dict[str, Any]
    trace: Annotated[list[dict[str, Any]], operator.add]


def _serializable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _safe_feature_sql(sql: str) -> tuple[str, list[str]]:
    statements = sqlglot.parse(sql, read="postgres")
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValueError("设备 Recipe 只允许单条 SELECT/CTE")
    tree = statements[0]
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command)
    if any(tree.find(kind) is not None for kind in forbidden):
        raise ValueError("设备 Recipe 包含禁止的 DDL/DML")
    cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    tables = sorted({
        f"{table.db}.{table.name}" if table.db else table.name
        for table in tree.find_all(exp.Table) if table.name and table.name not in cte_names
    })
    if not set(tables).issubset(ALLOWED_FEATURE_TABLES):
        raise ValueError(f"设备 Recipe 引用了未审核表：{tables}")
    return tree.sql(dialect="postgres", pretty=True), tables


class EquipmentAnomalyGraph:
    def __init__(self, settings: Settings) -> None:
        self.gateway = DeepSeekGateway(settings)
        builder = StateGraph(EquipmentState)
        builder.add_node("load_recipe", self.load_recipe)
        builder.add_node("execute_feature_sql", self.execute_feature_sql)
        builder.add_node("isolation_forest", self.isolation_forest)
        builder.add_node("explain_deviation", self.explain_deviation)
        builder.add_node("compose_diagnosis", self.compose_diagnosis)
        builder.add_edge(START, "load_recipe")
        builder.add_edge("load_recipe", "execute_feature_sql")
        builder.add_edge("execute_feature_sql", "isolation_forest")
        builder.add_edge("isolation_forest", "explain_deviation")
        builder.add_edge("explain_deviation", "compose_diagnosis")
        builder.add_edge("compose_diagnosis", END)
        self.graph = builder.compile()

    def invoke(self, run_id: str) -> EquipmentState:
        return self.graph.invoke({"run_id": run_id, "trace": []})

    def load_recipe(self, _: EquipmentState) -> dict[str, Any]:
        started = time.perf_counter()
        with get_engine().connect() as connection:
            recipe = dict(connection.execute(text(
                "SELECT * FROM app.analysis_recipe WHERE recipe_code='equipment-daily-iforest-v1' AND status='published'"
            )).mappings().one())
        safe_sql, tables = _safe_feature_sql(recipe["feature_sql"])
        bundle = retrieve_evidence("本月各设备非计划停机时长排名", top_k=8)
        recipe["feature_sql"] = safe_sql
        evidence = {
            "metric": bundle["metric"]["metric_name"], "formula": bundle["metric"]["formula"],
            "tables": tables, "rules": [rule["rule_content"] for rule in bundle["rules"]],
            "retrieval": bundle["retrieval"], "sources": [item["title"] for item in bundle["items"][:5]],
        }
        return {
            "recipe": recipe, "evidence": evidence,
            "trace": _trace("load_recipe", "审核 Recipe 与 RAG", started,
                            f"载入 {recipe['algorithm_name']} v{recipe['version']}，Feature SQL 仅访问 {len(tables)} 张审核表",
                            {"recipe_code": recipe["recipe_code"], "tables": tables, "feature_count": len(recipe["feature_columns"])}),
        }

    def execute_feature_sql(self, state: EquipmentState) -> dict[str, Any]:
        started = time.perf_counter()
        with get_engine().connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                connection.execute(text(f"EXPLAIN (FORMAT JSON) {state['recipe']['feature_sql']}"))
                result = connection.execute(text(state["recipe"]["feature_sql"]))
                rows = [{key: _serializable(value) for key, value in dict(row).items()} for row in result.mappings().all()]
            finally:
                transaction.rollback()
        baseline = [row for row in rows if row["business_date"] <= "2025-11-30"]
        current = [row for row in rows if row["business_date"] >= "2025-12-01"]
        if len(baseline) < 100 or len(current) < 100:
            raise ValueError("设备 Recipe 的训练或评分样本不足")
        return {
            "feature_rows": current, "baseline_rows": baseline,
            "trace": _trace("execute_feature_sql", "日粒度特征 SQL", started,
                            f"EXPLAIN 与只读执行通过：{len(baseline)} 行历史基线，{len(current)} 行当前评分样本",
                            {"baseline_rows": len(baseline), "scoring_rows": len(current), "timeout_ms": 5000}),
        }

    def isolation_forest(self, state: EquipmentState) -> dict[str, Any]:
        started = time.perf_counter()
        features = list(state["recipe"]["feature_columns"])
        params = dict(state["recipe"]["parameters"])
        baseline_matrix = np.asarray([[float(row[name]) for name in features] for row in state["baseline_rows"]], dtype=float)
        current_matrix = np.asarray([[float(row[name]) for name in features] for row in state["feature_rows"]], dtype=float)
        scaler = StandardScaler().fit(baseline_matrix)
        model = IsolationForest(
            n_estimators=int(params["n_estimators"]), contamination=float(params["contamination"]),
            random_state=int(params["random_state"]), n_jobs=1,
        ).fit(scaler.transform(baseline_matrix))
        transformed = scaler.transform(current_matrix)
        raw_scores = -model.decision_function(transformed)
        predictions = model.predict(transformed)
        low, high = float(raw_scores.min()), float(raw_scores.max())
        span = max(high - low, 1e-9)
        scored: list[dict[str, Any]] = []
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row, raw_score, prediction in zip(state["feature_rows"], raw_scores, predictions, strict=True):
            item = {**row, "anomaly_score": round(100 * (float(raw_score) - low) / span, 2), "is_anomaly": bool(prediction == -1)}
            scored.append(item)
            grouped[item["equipment_id"]].append(item)
        ranking = []
        for equipment_rows in grouped.values():
            anomaly_rows = [item for item in equipment_rows if item["is_anomaly"]]
            ranking.append({
                "equipment_id": equipment_rows[0]["equipment_id"], "equipment_name": equipment_rows[0]["equipment_name"],
                "equipment_type": equipment_rows[0]["equipment_type"], "line_name": equipment_rows[0]["line_name"],
                "anomaly_days": len(anomaly_rows), "max_anomaly_score": max(item["anomaly_score"] for item in equipment_rows),
                "total_downtime_minutes": round(sum(float(item["downtime_minutes"]) for item in equipment_rows), 2),
                "max_single_duration": max(float(item["max_downtime_minutes"]) for item in equipment_rows),
                "alarm_count": int(sum(int(item["alarm_count"]) for item in equipment_rows)),
            })
        ranking.sort(key=lambda item: (-item["anomaly_days"], -item["max_anomaly_score"], item["equipment_id"]))
        return {
            "scored_rows": scored, "ranking": ranking,
            "trace": _trace("isolation_forest", "Isolation Forest 评分", started,
                            f"固定随机种子完成 {len(scored)} 个设备日评分，识别 {sum(item['is_anomaly'] for item in scored)} 个异常日",
                            {"algorithm": "IsolationForest", "version": state["recipe"]["version"], "parameters": params}),
        }

    def explain_deviation(self, state: EquipmentState) -> dict[str, Any]:
        started = time.perf_counter()
        top = state["ranking"][0]
        equipment_rows = [row for row in state["scored_rows"] if row["equipment_id"] == top["equipment_id"]]
        top_day = max(equipment_rows, key=lambda row: row["anomaly_score"])
        baseline = [row for row in state["baseline_rows"] if row["equipment_id"] == top["equipment_id"]]
        deviations = []
        labels = {
            "downtime_minutes": "日停机总时长", "downtime_count": "日停机次数", "alarm_count": "日报警次数",
            "avg_downtime_minutes": "平均停机时长", "max_downtime_minutes": "最大单次停机", "planned_event_ratio": "计划事件占比",
            "reason_diversity": "事件原因多样性",
        }
        for feature in state["recipe"]["feature_columns"]:
            history = np.asarray([float(row[feature]) for row in baseline], dtype=float)
            median = float(np.median(history))
            q1, q3 = np.percentile(history, [25, 75])
            scale = max(float(q3 - q1), 1.0)
            current = float(top_day[feature])
            deviations.append({
                "feature": feature, "label": labels[feature], "current": round(current, 2), "baseline_median": round(median, 2),
                "robust_deviation": round((current - median) / scale, 2),
                "change_pct": round(100 * (current - median) / median, 1) if median else None,
            })
        deviations.sort(key=lambda item: -abs(item["robust_deviation"]))
        with get_engine().connect() as connection:
            reasons = [{key: _serializable(value) for key, value in dict(row).items()} for row in connection.execute(text("""
                SELECT event_reason, COUNT(*) AS event_count, ROUND(SUM(duration_minutes), 2) AS duration_minutes
                FROM demo.fact_equipment_event
                WHERE equipment_id=:equipment_id AND start_time::date BETWEEN DATE '2025-12-01' AND DATE '2025-12-29'
                GROUP BY event_reason ORDER BY duration_minutes DESC, event_reason
            """), {"equipment_id": top["equipment_id"]}).mappings()]
        assessment = {
            "top_equipment": top, "top_anomaly_date": top_day["business_date"],
            "top_anomaly_score": top_day["anomaly_score"],
            "anomaly_rate_pct": round(100 * top["anomaly_days"] / len(equipment_rows), 1),
            "status": "high" if top["anomaly_days"] >= 5 else "attention",
        }
        timeline = [{"business_date": row["business_date"], "anomaly_score": row["anomaly_score"], "is_anomaly": row["is_anomaly"], "downtime_minutes": row["downtime_minutes"]} for row in equipment_rows]
        return {
            "assessment": assessment, "timeline": timeline,
            "reason_distribution": reasons, "deviations": deviations[:5],
            "trace": _trace("explain_deviation", "稳健特征偏离解释", started,
                            f"锁定 {top['equipment_name']}，以历史中位数/IQR 解释前 {min(5, len(deviations))} 项偏离",
                            {"top_equipment": top["equipment_id"], "top_date": top_day["business_date"], "method": "median + IQR"}),
        }

    def compose_diagnosis(self, state: EquipmentState) -> dict[str, Any]:
        started = time.perf_counter()
        system_prompt = """你是制造业设备可靠性 Agent。根据 Isolation Forest 结果输出 JSON：headline、summary、risks(2-4条)、actions(2-4条)。
必须指出异常设备、异常天数、最大单次停机和最显著特征偏离；事件原因只能作为核查线索，不得宣称算法发现了因果根因；行动项应具体且可执行。"""
        payload = {
            "period": "2025-12-01..2025-12-29", "assessment": state["assessment"],
            "deviations": state["deviations"], "reason_distribution": state["reason_distribution"],
        }
        try:
            generated = self.gateway.complete_json(system_prompt=system_prompt, user_prompt=json.dumps(payload, ensure_ascii=False, default=str))
            normalized = {
                "headline": str(generated.get("headline", ""))[:80],
                "summary": str(generated.get("summary", ""))[:600],
                "risks": [str(item)[:240] for item in generated.get("risks", [])[:4]],
                "actions": [str(item)[:240] for item in generated.get("actions", [])[:4]],
            }
            brief = EquipmentBriefContract.model_validate(normalized).model_dump()
            mode = "deepseek"
        except (ValueError, ValidationError, json.JSONDecodeError):
            top = state["assessment"]["top_equipment"]
            first = state["deviations"][0]
            brief = {
                "headline": f"{top['equipment_name']}出现持续性设备日异常",
                "summary": f"评分窗口内识别 {top['anomaly_days']} 个异常日，最大单次停机 {top['max_single_duration']} 分钟。最显著偏离为{first['label']}，当前值 {first['current']}，历史中位数 {first['baseline_median']}。",
                "risks": ["异常行为持续出现，可能影响生产节拍", "现有事件原因仅能作为进一步核查线索"],
                "actions": ["核查异常日期对应的维修、点检和工艺记录", "对高偏离特征设置短周期复测与告警阈值"],
            }
            mode = "guarded_fallback"
        brief["generation_mode"] = mode
        return {
            "brief": brief,
            "trace": _trace("compose_diagnosis", "DeepSeek 设备诊断", started,
                            f"基于算法输出与偏离证据生成设备简报（{mode}）", {"mode": mode, "risk_count": len(brief["risks"])}),
        }
