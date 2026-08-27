from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import text

from app.core.database import get_engine
from app.rag.embedding import embed_texts, vector_literal


TOPIC_TERMS = {
    "quality": ("质量", "良率", "合格率", "不良率", "缺陷率", "缺陷", "Pareto", "帕累托", "环比", "检验", "工序", "产品"),
    "equipment": ("设备", "停机", "宕机", "报警", "故障", "异常"),
    "production": ("生产", "产量", "完工", "计划", "达成率", "完成率", "产线", "趋势"),
}


def _topic(question: str) -> str | None:
    # Domain nouns take precedence over generic analytical words.  In
    # particular, "非计划停机趋势" contains both "计划" and "趋势", but is
    # unequivocally an equipment question rather than a production question.
    if any(term in question for term in ("设备", "停机", "宕机", "报警", "故障")):
        return "equipment"
    if any(term in question for term in ("质量", "良率", "合格率", "不良率", "缺陷率", "缺陷", "检验")):
        return "quality"
    if any(term in question for term in ("生产", "产量", "完工", "达成率", "完成率", "产线")):
        return "production"
    scored = {topic: sum(term in question for term in terms) for topic, terms in TOPIC_TERMS.items()}
    topic, score = max(scored.items(), key=lambda item: item[1])
    return topic if score else None


def _expanded_terms(question: str) -> list[str]:
    terms = {question}
    with get_engine().connect() as connection:
        synonyms = connection.execute(text("SELECT canonical_term, synonym_term FROM app.synonym")).mappings().all()
        metrics = connection.execute(text("SELECT metric_name FROM app.metric WHERE status='published'")).scalars().all()
    for item in synonyms:
        if item["canonical_term"] in question or item["synonym_term"] in question:
            terms.update((item["canonical_term"], item["synonym_term"]))
    terms.update(metric for metric in metrics if metric in question)
    terms.update(term for values in TOPIC_TERMS.values() for term in values if term in question)
    return sorted(terms, key=len, reverse=True)


def _explicit_metric_code(question: str, topic: str | None) -> str | None:
    if topic == "quality" and any(term in question for term in ("Pareto", "帕累托", "缺陷类型", "缺陷数量")):
        return "defect_count"
    if topic == "equipment":
        if "报警" in question and "次数" in question:
            return "alarm_count"
        if any(term in question for term in ("停机", "宕机")):
            return "downtime_count" if "次数" in question else "downtime_minutes"
    with get_engine().connect() as connection:
        metrics = [dict(row) for row in connection.execute(text(
            "SELECT metric_code, metric_name, topic_code FROM app.metric WHERE status='published' ORDER BY length(metric_name) DESC"
        )).mappings()]
        synonyms = [dict(row) for row in connection.execute(text(
            "SELECT topic_code, canonical_term, synonym_term FROM app.synonym ORDER BY length(synonym_term) DESC"
        )).mappings()]
    for item in synonyms:
        if (topic is None or item["topic_code"] == topic) and item["synonym_term"] in question:
            match = next((metric for metric in metrics if metric["topic_code"] == item["topic_code"] and metric["metric_name"] == item["canonical_term"]), None)
            if match:
                return match["metric_code"]
    for metric in metrics:
        if (topic is None or metric["topic_code"] == topic) and metric["metric_name"] in question:
            return metric["metric_code"]
    topic_metrics = [metric for metric in metrics if metric["topic_code"] == topic]
    if len(topic_metrics) == 1:
        return topic_metrics[0]["metric_code"]
    return None


def _ranked_channels(question: str) -> tuple[dict[str, list[dict[str, Any]]], str | None]:
    query_vector = vector_literal(embed_texts([question])[0])
    topic = _topic(question)
    terms = _expanded_terms(question)
    with get_engine().connect() as connection:
        all_chunks = [dict(row) for row in connection.execute(text("""
            SELECT id, source_type, source_id, topic_code, title, content, metadata
            FROM app.knowledge_chunk
        """)).mappings()]
        fuzzy = [dict(row) for row in connection.execute(text("""
            SELECT id, source_type, source_id, topic_code, title, content, metadata,
                   GREATEST(similarity(title, :question), similarity(content, :question)) AS channel_score
            FROM app.knowledge_chunk
            WHERE (CAST(:topic AS text) IS NULL OR topic_code IS NULL OR topic_code=CAST(:topic AS text))
            ORDER BY channel_score DESC, id LIMIT 14
        """), {"question": question, "topic": topic}).mappings()]
        vector = [dict(row) for row in connection.execute(text("""
            SELECT id, source_type, source_id, topic_code, title, content, metadata,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS channel_score
            FROM app.knowledge_chunk
            WHERE embedding IS NOT NULL AND (CAST(:topic AS text) IS NULL OR topic_code IS NULL OR topic_code=CAST(:topic AS text))
            ORDER BY embedding <=> CAST(:embedding AS vector), id LIMIT 14
        """), {"embedding": query_vector, "topic": topic}).mappings()]

    exact: list[dict[str, Any]] = []
    for item in all_chunks:
        if topic and item["topic_code"] not in (None, topic):
            continue
        haystack = f"{item['title']} {item['content']}".lower()
        score = sum((3 if term.lower() in item["title"].lower() else 1) for term in terms if term.lower() in haystack)
        if score:
            item["channel_score"] = float(score)
            exact.append(item)
    exact.sort(key=lambda item: (-item["channel_score"], item["id"]))
    return {"exact": exact[:14], "fuzzy": fuzzy, "vector": vector}, topic


def retrieve_evidence(question: str, top_k: int = 10) -> dict[str, Any]:
    channels, topic = _ranked_channels(question)
    if topic is None:
        raise ValueError("当前比赛版仅支持包含明确制造主题和已发布指标的分析问题")
    fused: dict[int, float] = defaultdict(float)
    contributions: dict[int, list[str]] = defaultdict(list)
    by_id: dict[int, dict[str, Any]] = {}
    weights = {"exact": 1.15, "fuzzy": 0.75, "vector": 1.0}
    for channel, items in channels.items():
        for rank, item in enumerate(items, start=1):
            chunk_id = item["id"]
            by_id[chunk_id] = item
            fused[chunk_id] += weights[channel] / (60 + rank)
            contributions[chunk_id].append(channel)
    ranked_ids = sorted(fused, key=lambda chunk_id: (-fused[chunk_id], chunk_id))[:top_k]
    items = [{
        "id": chunk_id, "source_type": by_id[chunk_id]["source_type"],
        "source_id": by_id[chunk_id]["source_id"], "title": by_id[chunk_id]["title"],
        "content": by_id[chunk_id]["content"], "metadata": by_id[chunk_id]["metadata"],
        "score": round(fused[chunk_id], 6), "channels": contributions[chunk_id],
    } for chunk_id in ranked_ids]

    explicit_metric = _explicit_metric_code(question, topic)
    if explicit_metric is None:
        raise ValueError("当前比赛版仅支持已发布的质量、设备或生产指标分析问题")
    metric_item = next((item for item in items if item["metadata"].get("kind") == "metric" and (explicit_metric is None or item["metadata"].get("metric_code") == explicit_metric)), None)
    if metric_item is None and explicit_metric:
        with get_engine().connect() as connection:
            row = connection.execute(text("""
                SELECT id, source_type, source_id, title, content, metadata
                FROM app.knowledge_chunk WHERE source_id=:source_id
            """), {"source_id": f"metric:{explicit_metric}"}).mappings().one_or_none()
        if row:
            metric_item = {**dict(row), "score": 1.0, "channels": ["exact"]}
            items.insert(0, metric_item)
    if metric_item is None:
        raise ValueError("RAG 未命中已发布指标，请换一种业务表述")
    metric_code = metric_item["metadata"]["metric_code"]

    candidate_tables: list[str] = list(metric_item["metadata"].get("mapped_tables", []))
    matching_example = next((item for item in items if item["metadata"].get("kind") == "example" and item["metadata"].get("metric_code") == metric_code), None)
    if matching_example:
        candidate_tables.extend(matching_example["metadata"].get("expected_tables", []))
    else:
        for item in items:
            metadata = item["metadata"]
            if metadata.get("kind") == "table":
                candidate_tables.append(metadata["table"])
    candidate_tables = list(dict.fromkeys(candidate_tables))[:6]

    with get_engine().connect() as connection:
        table_rows = [dict(row) for row in connection.execute(text("""
            SELECT t.schema_name || '.' || t.table_name AS table_name, t.display_name, t.description,
                   jsonb_agg(jsonb_build_object('name', c.column_name, 'type', c.data_type, 'description', c.description)
                             ORDER BY c.ordinal_position) AS columns
            FROM app.catalog_table t JOIN app.catalog_column c ON c.catalog_table_id=t.id
            WHERE t.schema_name || '.' || t.table_name = ANY(:tables)
            GROUP BY t.id ORDER BY array_position(:tables, t.schema_name || '.' || t.table_name)
        """), {"tables": candidate_tables}).mappings()]
        relations = [dict(row) for row in connection.execute(text("""
            SELECT 'demo.' || src.table_name AS source_table, r.source_column,
                   'demo.' || tgt.table_name AS target_table, r.target_column, r.cardinality
            FROM app.catalog_relation r
            JOIN app.catalog_table src ON src.id=r.source_table_id
            JOIN app.catalog_table tgt ON tgt.id=r.target_table_id
            WHERE ('demo.' || src.table_name = ANY(:tables) AND 'demo.' || tgt.table_name = ANY(:tables))
            ORDER BY src.table_name, tgt.table_name
        """), {"tables": candidate_tables}).mappings()]
        metric = dict(connection.execute(text("SELECT * FROM app.metric WHERE metric_code=:code"), {"code": metric_code}).mappings().one())
        rules = [dict(row) for row in connection.execute(text("SELECT rule_code, rule_name, rule_content, severity FROM app.business_rule WHERE topic_code=:topic ORDER BY rule_code"), {"topic": metric["topic_code"]}).mappings()]
        full_schema_chars = connection.execute(text("SELECT COALESCE(SUM(length(title) + length(content)),0) FROM app.knowledge_chunk")).scalar_one()

    evidence_chars = sum(len(item["title"]) + len(item["content"]) for item in items) + sum(len(table["description"]) + sum(len(column["name"]) + len(column["type"]) + len(column.get("description") or "") for column in table["columns"]) for table in table_rows)
    return {
        "query": question, "topic_code": metric["topic_code"], "metric": metric,
        "items": items, "tables": table_rows, "relations": relations, "rules": rules,
        "examples": [item["metadata"] for item in items if item["metadata"].get("kind") == "example" and item["metadata"].get("metric_code") == metric_code][:2],
        "retrieval": {
            "strategy": "exact + pg_trgm + bge-small-zh-v1.5 / RRF",
            "top_k": len(items), "channel_hits": {key: len(value) for key, value in channels.items()},
            "full_schema_chars": full_schema_chars, "evidence_chars": evidence_chars,
            "context_reduction_pct": round(max(0, 100 * (1 - evidence_chars / max(full_schema_chars, 1))), 1),
        },
    }


def bundle_for_prompt(bundle: dict[str, Any]) -> str:
    compact = {
        "topic_code": bundle["topic_code"],
        "metric": {key: bundle["metric"][key] for key in ("metric_code", "metric_name", "description", "formula", "unit", "grain", "dimensions")},
        "rules": bundle["rules"], "tables": bundle["tables"], "relations": bundle["relations"],
        "validated_examples": bundle["examples"],
    }
    return json.dumps(compact, ensure_ascii=False, default=str)
