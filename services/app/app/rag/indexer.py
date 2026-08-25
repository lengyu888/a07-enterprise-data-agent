from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import get_engine
from app.rag.embedding import embed_texts, vector_literal


@dataclass(frozen=True)
class ChunkDocument:
    source_type: str
    source_id: str
    topic_code: str | None
    title: str
    content: str
    metadata: dict[str, Any]

    @property
    def content_hash(self) -> str:
        model = get_settings().embedding_model
        value = f"{model}\n{self.title}\n{self.content}\n{json.dumps(self.metadata, ensure_ascii=False, sort_keys=True, default=str)}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _documents() -> list[ChunkDocument]:
    documents: list[ChunkDocument] = []
    with get_engine().connect() as connection:
        metrics = connection.execute(text("SELECT * FROM app.metric WHERE status='published' ORDER BY metric_code")).mappings().all()
        rules = connection.execute(text("SELECT * FROM app.business_rule ORDER BY rule_code")).mappings().all()
        objects = connection.execute(text("SELECT * FROM app.business_object ORDER BY object_code")).mappings().all()
        tables = connection.execute(text("""
            SELECT t.id, t.schema_name, t.table_name, t.display_name, t.description, t.business_domain,
                   jsonb_agg(jsonb_build_object(
                       'name', c.column_name, 'type', c.data_type, 'description', c.description,
                       'samples', c.sample_values, 'primary_key', c.is_primary_key
                   ) ORDER BY c.ordinal_position) AS columns
            FROM app.catalog_table t
            JOIN app.catalog_column c ON c.catalog_table_id=t.id
            WHERE t.schema_name='demo'
            GROUP BY t.id ORDER BY t.table_name
        """)).mappings().all()
        relations = connection.execute(text("""
            SELECT r.id, src.table_name AS source_table, r.source_column,
                   tgt.table_name AS target_table, r.target_column,
                   r.cardinality, r.description
            FROM app.catalog_relation r
            JOIN app.catalog_table src ON src.id=r.source_table_id
            JOIN app.catalog_table tgt ON tgt.id=r.target_table_id
            ORDER BY src.table_name, tgt.table_name
        """)).mappings().all()
        cases = connection.execute(text("SELECT * FROM app.validation_case ORDER BY case_code")).mappings().all()

    for item in metrics:
        metadata = {
            "kind": "metric", "metric_code": item["metric_code"], "formula": item["formula"],
            "unit": item["unit"], "grain": item["grain"], "dimensions": item["dimensions"],
            "mapped_tables": item["mapped_tables"], "version": item["version"],
        }
        documents.append(ChunkDocument(
            "business", f"metric:{item['metric_code']}", item["topic_code"], f"指标：{item['metric_name']}",
            f"{item['metric_name']}。{item['description']}。计算公式：{item['formula']}。统计粒度：{item['grain']}。可用维度：{'、'.join(item['dimensions'])}。",
            metadata,
        ))
    for item in rules:
        documents.append(ChunkDocument(
            "business", f"rule:{item['rule_code']}", item["topic_code"], f"强规则：{item['rule_name']}",
            item["rule_content"], {"kind": "rule", "rule_code": item["rule_code"], "severity": item["severity"]},
        ))
    for item in objects:
        documents.append(ChunkDocument(
            "business", f"object:{item['object_code']}", item["topic_code"], f"业务对象：{item['object_name']}",
            f"{item['description']}。映射数据表：{'、'.join(item['mapped_tables'])}。",
            {"kind": "object", "object_code": item["object_code"], "mapped_tables": item["mapped_tables"]},
        ))
    for item in tables:
        table_name = f"{item['schema_name']}.{item['table_name']}"
        column_text = "；".join(
            f"{column['name']}({column['type']})：{column.get('description') or '无说明'}"
            for column in item["columns"]
        )
        documents.append(ChunkDocument(
            "schema", f"table:{table_name}", None, f"数据表：{item['display_name']} / {table_name}",
            f"{item['description']}。业务域：{item['business_domain']}。字段：{column_text}",
            {"kind": "table", "table": table_name, "display_name": item["display_name"], "columns": item["columns"]},
        ))
    for item in relations:
        source = f"demo.{item['source_table']}"
        target = f"demo.{item['target_table']}"
        documents.append(ChunkDocument(
            "relation", f"relation:{item['id']}", None, f"Join：{source} → {target}",
            f"真实外键关系：{source}.{item['source_column']} = {target}.{item['target_column']}，基数 {item['cardinality']}。{item['description']}",
            {"kind": "relation", "source_table": source, "source_column": item["source_column"], "target_table": target, "target_column": item["target_column"], "cardinality": item["cardinality"]},
        ))
    for item in cases:
        documents.append(ChunkDocument(
            "example", f"case:{item['case_code']}", item["scene"], f"验证案例：{item['question']}",
            f"已审核问题：{item['question']}。指标：{item['metric_code']}。说明：{item['notes']}。SQL 结构：{item['sql_template']}",
            {"kind": "example", "case_code": item["case_code"], "question": item["question"], "metric_code": item["metric_code"], "sql_template": item["sql_template"], "expected_tables": item["expected_tables"]},
        ))
    return documents


def refresh_index() -> dict[str, Any]:
    documents = _documents()
    keys = {(item.source_type, item.source_id) for item in documents}
    with get_engine().connect() as connection:
        existing = {
            (row["source_type"], row["source_id"]): row["content_hash"]
            for row in connection.execute(text("SELECT source_type, source_id, content_hash FROM app.knowledge_chunk")).mappings()
        }
    changed = [item for item in documents if existing.get((item.source_type, item.source_id)) != item.content_hash]
    embeddings = embed_texts([f"{item.title}\n{item.content}" for item in changed])

    with get_engine().begin() as connection:
        for item, embedding in zip(changed, embeddings, strict=True):
            connection.execute(text("""
                INSERT INTO app.knowledge_chunk
                    (source_type, source_id, topic_code, title, content, metadata, content_hash, embedding, updated_at)
                VALUES (:source_type, :source_id, :topic_code, :title, :content,
                        CAST(:metadata AS jsonb), :content_hash, CAST(:embedding AS vector), NOW())
                ON CONFLICT (source_type, source_id) DO UPDATE SET
                    topic_code=EXCLUDED.topic_code, title=EXCLUDED.title, content=EXCLUDED.content,
                    metadata=EXCLUDED.metadata, content_hash=EXCLUDED.content_hash,
                    embedding=EXCLUDED.embedding, updated_at=NOW()
            """), {
                "source_type": item.source_type, "source_id": item.source_id,
                "topic_code": item.topic_code, "title": item.title, "content": item.content,
                "metadata": json.dumps(item.metadata, ensure_ascii=False, default=str),
                "content_hash": item.content_hash, "embedding": vector_literal(embedding),
            })
        stale = set(existing) - keys
        for source_type, source_id in stale:
            connection.execute(text("DELETE FROM app.knowledge_chunk WHERE source_type=:source_type AND source_id=:source_id"), {"source_type": source_type, "source_id": source_id})
    return {"total": len(documents), "embedded": len(changed), "removed": len(set(existing) - keys), "model": get_settings().embedding_model, "dimensions": 512}


def ensure_index() -> dict[str, Any]:
    return refresh_index()
