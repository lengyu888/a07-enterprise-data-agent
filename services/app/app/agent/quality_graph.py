from __future__ import annotations

import json
import operator
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

import sqlglot
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlglot import exp
from typing_extensions import TypedDict

from app.core.config import Settings
from app.core.database import get_engine
from app.integrations.deepseek import DeepSeekGateway


SUPPORTED_QUESTION = "分析本月各工序良率，找出良率最低的工序"
ALLOWED_TABLES = {"demo.fact_quality_inspection", "demo.dim_process"}
FALLBACK_SQL = """SELECT
    p.process_name,
    ROUND(100.0 * SUM(q.qualified_qty) / NULLIF(SUM(q.inspected_qty), 0), 2) AS yield_rate,
    SUM(q.inspected_qty) AS inspected_qty
FROM demo.fact_quality_inspection AS q
JOIN demo.dim_process AS p ON p.process_id = q.process_id
WHERE q.inspection_time::date BETWEEN DATE '2025-12-01' AND DATE '2025-12-29'
GROUP BY p.process_name
ORDER BY yield_rate ASC
LIMIT 20"""


class SqlGeneration(BaseModel):
    sql: str = Field(min_length=20)
    rationale: str = Field(min_length=4, max_length=500)


class AgentState(TypedDict, total=False):
    question: str
    run_id: str
    scene: str
    metric: dict[str, Any]
    rule: dict[str, Any]
    tables: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    plan: list[str]
    time_range: dict[str, str]
    sql: str
    generation_mode: str
    sql_rationale: str
    referenced_tables: list[str]
    columns: list[str]
    rows: list[dict[str, Any]]
    chart_spec: dict[str, Any]
    answer: str
    trace: Annotated[list[dict[str, Any]], operator.add]


def _serializable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _trace(node: str, name: str, started: float, summary: str, payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [{
        "node_name": node,
        "display_name": name,
        "status": "completed",
        "duration_ms": max(1, round((time.perf_counter() - started) * 1000)),
        "summary": summary,
        "payload": payload or {},
    }]


class QualityThinSliceGraph:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.gateway = DeepSeekGateway(settings)
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("understand", self.understand)
        builder.add_node("retrieve", self.retrieve)
        builder.add_node("plan", self.plan)
        builder.add_node("text_to_sql", self.text_to_sql)
        builder.add_node("validate_sql", self.validate_sql)
        builder.add_node("execute_sql", self.execute_sql)
        builder.add_node("build_chart", self.build_chart)
        builder.add_node("summarize", self.summarize)
        builder.add_edge(START, "understand")
        builder.add_edge("understand", "retrieve")
        builder.add_edge("retrieve", "plan")
        builder.add_edge("plan", "text_to_sql")
        builder.add_edge("text_to_sql", "validate_sql")
        builder.add_edge("validate_sql", "execute_sql")
        builder.add_edge("execute_sql", "build_chart")
        builder.add_edge("build_chart", "summarize")
        builder.add_edge("summarize", END)
        return builder.compile()

    def invoke(self, question: str, run_id: str) -> AgentState:
        return self.graph.invoke({"question": question, "run_id": run_id, "trace": []})

    def understand(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        normalized = state["question"].strip()
        if not any(term in normalized for term in ("良率", "合格率")) or "工序" not in normalized:
            raise ValueError(f"阶段 2 MVP 仅支持：{SUPPORTED_QUESTION}")
        return {
            "scene": "quality",
            "trace": _trace("understand", "问题理解", started, "识别为质量分析 / 工序良率问题", {"scene": "quality", "metric": "yield_rate"}),
        }

    def retrieve(self, _: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        engine = get_engine()
        with engine.connect() as connection:
            metric = dict(connection.execute(text("SELECT * FROM app.metric WHERE metric_code='yield_rate' AND status='published'")).mappings().one())
            rule = dict(connection.execute(text("SELECT * FROM app.business_rule WHERE rule_code='quality-yield-source'")).mappings().one())
            tables = [dict(row) for row in connection.execute(text("""
                SELECT t.table_name, t.display_name, t.description,
                       jsonb_agg(jsonb_build_object('name', c.column_name, 'type', c.data_type, 'description', c.description) ORDER BY c.ordinal_position) AS columns
                FROM app.catalog_table t JOIN app.catalog_column c ON c.catalog_table_id=t.id
                WHERE t.schema_name='demo' AND t.table_name IN ('fact_quality_inspection', 'dim_process')
                GROUP BY t.id ORDER BY t.table_name
            """)).mappings()]
            relations = [dict(row) for row in connection.execute(text("""
                SELECT src.table_name AS source_table, r.source_column, tgt.table_name AS target_table, r.target_column
                FROM app.catalog_relation r
                JOIN app.catalog_table src ON src.id=r.source_table_id
                JOIN app.catalog_table tgt ON tgt.id=r.target_table_id
                WHERE src.table_name='fact_quality_inspection' AND tgt.table_name='dim_process'
            """)).mappings()]
        evidence_count = 2 + len(tables) + len(relations)
        return {
            "metric": metric,
            "rule": rule,
            "tables": tables,
            "relations": relations,
            "trace": _trace("retrieve", "精确证据检索", started, f"命中良率口径、强规则、2 张表和 {len(relations)} 条 Join 关系", {"evidence_count": evidence_count, "tables": [f"demo.{item['table_name']}" for item in tables]}),
        }

    def plan(self, _: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        plan = [
            "将“本月”解析为固定业务日期所在月份",
            "按 process_id 聚合检验数与合格数",
            "连接工序主数据获取工序名称",
            "计算良率并按升序找出最低工序",
        ]
        period = {"start": "2025-12-01", "end": "2025-12-29", "anchor": "2025-12-29"}
        return {"plan": plan, "time_range": period, "trace": _trace("plan", "分析计划", started, "生成 4 步质量分析计划并解析业务时间", {"steps": plan, "time_range": period})}

    def text_to_sql(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        evidence = {
            "metric": {key: state["metric"][key] for key in ("metric_name", "formula", "grain", "mapped_tables")},
            "rule": state["rule"]["rule_content"],
            "tables": state["tables"],
            "relations": state["relations"],
            "time_range": state["time_range"],
        }
        system_prompt = """你是制造业 PostgreSQL Text-to-SQL 节点。只使用给定证据生成一条只读 SELECT。
必须返回 JSON 对象：{\"sql\": \"...\", \"rationale\": \"...\"}。
SQL 必须输出 process_name、yield_rate、inspected_qty；yield_rate 使用百分数并保留两位；
必须返回全部工序用于对比图，按 yield_rate 升序即可，不得用 LIMIT 1、排名过滤等方式只保留最低工序；
只能访问 demo.fact_quality_inspection 和 demo.dim_process；必须使用明确日期边界；不得使用注释、DDL、DML 或多个语句；LIMIT 不超过 100。"""
        user_prompt = f"用户问题：{state['question']}\n证据：{json.dumps(evidence, ensure_ascii=False, default=str)}"
        generation_mode = "deepseek"
        try:
            generated = SqlGeneration.model_validate(self.gateway.complete_json(system_prompt=system_prompt, user_prompt=user_prompt))
            sql = generated.sql.strip().rstrip(";")
            rationale = generated.rationale
        except (ValueError, ValidationError, json.JSONDecodeError):
            sql = FALLBACK_SQL
            rationale = "模型结构化输出未通过契约，使用同证据生成的已审核 SQL 模板。"
            generation_mode = "guarded_fallback"
        return {
            "sql": sql,
            "generation_mode": generation_mode,
            "sql_rationale": rationale,
            "trace": _trace("text_to_sql", "DeepSeek Text-to-SQL", started, f"生成 SQL（{generation_mode}）", {"model": self.settings.deepseek_model, "mode": generation_mode}),
        }

    def validate_sql(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            statements = sqlglot.parse(state["sql"], read="postgres")
        except sqlglot.errors.ParseError as exc:
            raise ValueError("SQLGlot 无法解析模型 SQL") from exc
        if len(statements) != 1 or not isinstance(statements[0], exp.Select):
            raise ValueError("只允许单条 SELECT")
        tree = statements[0]
        forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command)
        if any(tree.find(kind) is not None for kind in forbidden):
            raise ValueError("SQL 包含禁止操作")
        cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
        referenced = sorted(
            {
                f"{table.db}.{table.name}" if table.db else table.name
                for table in tree.find_all(exp.Table)
                if table.name not in cte_names
            }
        )
        if set(referenced) != ALLOWED_TABLES:
            raise ValueError(f"SQL 表范围不符合证据：{referenced}")
        required_tokens = (
            "qualified_qty",
            "inspected_qty",
            "process_id",
            "inspection_time",
            "2025-12",
            "process_name",
            "yield_rate",
        )
        if not all(token in state["sql"] for token in required_tokens):
            raise ValueError("SQL 缺少良率口径、Join 键或时间边界")
        normalized_limit = False
        lower_sql = state["sql"].lower()
        if any(token in lower_sql for token in ("row_number(", "rank(", "dense_rank(")):
            raise ValueError("SQL 不得用排名窗口收窄全部工序结果")
        limit = tree.args.get("limit")
        if limit is None:
            tree = tree.limit(100)
        elif isinstance(limit.expression, exp.Literal) and limit.expression.is_int and int(limit.expression.this) < 3:
            tree = tree.limit(100, copy=False)
            normalized_limit = True
        safe_sql = tree.sql(dialect="postgres", pretty=True)
        validation_summary = "SQLGlot 通过：单条只读 SELECT、表白名单、口径与时间边界完整"
        if normalized_limit:
            validation_summary += "；已将过窄结果限制规范化为 100 行"
        return {
            "sql": safe_sql,
            "referenced_tables": referenced,
            "trace": _trace("validate_sql", "SQL 安全校验", started, validation_summary, {"referenced_tables": referenced, "row_limit": 100, "normalized_limit": normalized_limit}),
        }

    def execute_sql(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        engine = get_engine()
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                result = connection.execute(text(state["sql"]))
                columns = list(result.keys())
                rows = [{key: _serializable(value) for key, value in dict(row).items()} for row in result.mappings().fetchmany(100)]
            finally:
                transaction.rollback()
        if not rows:
            raise ValueError("查询结果为空")
        return {"columns": columns, "rows": rows, "trace": _trace("execute_sql", "只读 SQL 执行", started, f"只读事务在 5 秒限时内返回 {len(rows)} 行", {"row_count": len(rows)})}

    def build_chart(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        chart_spec = {
            "type": "bar",
            "title": "2025 年 12 月各工序良率",
            "x_field": "process_name",
            "y_field": "yield_rate",
            "unit": "%",
            "categories": [row["process_name"] for row in state["rows"]],
            "series": [{"name": "良率", "data": [row["yield_rate"] for row in state["rows"]]}],
        }
        return {"chart_spec": chart_spec, "trace": _trace("build_chart", "图表生成", started, "将真实查询结果转换为工序良率柱状图", {"chart_type": "bar", "points": len(state["rows"])})}

    def summarize(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        lowest = min(state["rows"], key=lambda row: float(row["yield_rate"]))
        system_prompt = "你是制造业质量分析师。仅依据给定查询结果，用中文输出 2-3 句简洁结论；必须指出最低工序、良率、时间范围，并声明结论基于检验数据，不推断未提供的根因。"
        user_prompt = json.dumps({"question": state["question"], "time_range": state["time_range"], "rows": state["rows"]}, ensure_ascii=False)
        try:
            answer = self.gateway.complete_text(system_prompt=system_prompt, user_prompt=user_prompt)
            if not answer:
                raise ValueError("empty answer")
        except Exception:
            answer = f"2025-12-01 至 2025-12-29，{lowest['process_name']}良率最低，为 {lowest['yield_rate']}%。结论仅基于当前检验数据，具体原因需结合缺陷与设备记录进一步分析。"
        return {"answer": answer, "trace": _trace("summarize", "DeepSeek 结论生成", started, f"基于 {len(state['rows'])} 行真实结果生成有据结论", {"lowest_process": lowest["process_name"], "lowest_yield": lowest["yield_rate"]})}
