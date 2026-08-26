from __future__ import annotations

import json
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import numpy as np
import sqlglot
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score, mean_absolute_error, r2_score, silhouette_score
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sqlalchemy import text
from sqlglot import exp

from app.core.database import get_engine


ALGORITHM_ORDER = [
    "LinearRegression",
    "LogisticRegression",
    "DecisionTree",
    "RandomForest",
    "KMeans",
    "IsolationForest",
]
ALLOWED_MODEL_TABLES = {
    "demo.fact_process_output", "demo.fact_work_order", "demo.dim_line",
    "demo.fact_quality_inspection", "demo.dim_process",
    "demo.fact_equipment_event", "demo.dim_equipment",
}


def _value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _validate_sql(sql: str) -> str:
    statements = sqlglot.parse(sql, read="postgres")
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValueError("算法 Recipe 只允许单条 SELECT/CTE")
    tree = statements[0]
    if any(tree.find(kind) is not None for kind in (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command)):
        raise ValueError("算法 Recipe 包含禁止的 DDL/DML")
    ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    tables = {
        f"{table.db}.{table.name}" if table.db else table.name
        for table in tree.find_all(exp.Table)
        if table.name and table.name not in ctes
    }
    if not tables.issubset(ALLOWED_MODEL_TABLES):
        raise ValueError(f"算法 Recipe 引用了未审核表：{sorted(tables)}")
    return tree.sql(dialect="postgres", pretty=True)


def list_algorithm_recipes() -> dict[str, Any]:
    with get_engine().connect() as connection:
        rows = [dict(row) for row in connection.execute(text("""
            SELECT recipe_code, scene, recipe_name, algorithm_name, version,
                   feature_columns, parameters, training_window, scoring_window,
                   explanation_rule, status
            FROM app.analysis_recipe WHERE status='published'
              AND algorithm_name = ANY(:algorithms)
        """), {"algorithms": ALGORITHM_ORDER}).mappings()]
        rows.sort(key=lambda item: ALGORITHM_ORDER.index(item["algorithm_name"]))
        latest = connection.execute(text("""
            SELECT run_id, status, algorithm_count, duration_ms, completed_at
            FROM app.algorithm_evaluation_run ORDER BY started_at DESC LIMIT 1
        """)).mappings().one_or_none()
    return {
        "count": len(rows),
        "algorithms": rows,
        "guardrails": ["仅运行已发布 Recipe", "SQLGlot 表白名单 + 只读事务", "固定时间切分与随机种子", "模型指标不包装为业务因果"],
        "latest_evaluation": dict(latest) if latest else None,
    }


def _execute_sql(connection: Any, sql: str) -> list[dict[str, Any]]:
    safe_sql = _validate_sql(sql)
    connection.execute(text(f"EXPLAIN (FORMAT JSON) {safe_sql}"))
    return [
        {key: _value(value) for key, value in dict(row).items()}
        for row in connection.execute(text(safe_sql)).mappings().all()
    ]


def _classification_result(algorithm: str, recipe: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    features = list(recipe["feature_columns"])
    train = [row for row in rows if row["business_date"] <= "2025-11-30"]
    valid = [row for row in rows if row["business_date"] >= "2025-12-01"]
    x_train = np.asarray([[float(row[name]) for name in features] for row in train], dtype=float)
    y_train = np.asarray([int(row["target"]) for row in train], dtype=int)
    x_valid = np.asarray([[float(row[name]) for name in features] for row in valid], dtype=float)
    y_valid = np.asarray([int(row["target"]) for row in valid], dtype=int)
    params = dict(recipe["parameters"])
    if algorithm == "LogisticRegression":
        scaler = StandardScaler().fit(x_train)
        model = LogisticRegression(
            max_iter=int(params["max_iter"]), class_weight=str(params["class_weight"]),
            random_state=int(params["random_state"]),
        ).fit(scaler.transform(x_train), y_train)
        prediction = model.predict(scaler.transform(x_valid))
        detail = {"iterations": int(model.n_iter_[0])}
    elif algorithm == "DecisionTree":
        model = DecisionTreeClassifier(
            max_depth=int(params["max_depth"]), min_samples_leaf=int(params["min_samples_leaf"]),
            class_weight=str(params["class_weight"]), random_state=int(params["random_state"]),
        ).fit(x_train, y_train)
        prediction = model.predict(x_valid)
        detail = {"tree_depth": int(model.get_depth()), "leaf_count": int(model.get_n_leaves())}
    else:
        model = RandomForestClassifier(
            n_estimators=int(params["n_estimators"]), max_depth=int(params["max_depth"]),
            min_samples_leaf=int(params["min_samples_leaf"]), class_weight=str(params["class_weight"]),
            random_state=int(params["random_state"]), n_jobs=1,
        ).fit(x_train, y_train)
        prediction = model.predict(x_valid)
        detail = {"trees": len(model.estimators_)}
    return {
        "algorithm": algorithm,
        "recipe_code": recipe["recipe_code"],
        "scene": recipe["scene"],
        "use_case": recipe["recipe_name"],
        "status": "passed",
        "split": {"method": "time_holdout", "training": recipe["training_window"], "validation": recipe["scoring_window"]},
        "rows": {"training": len(train), "validation": len(valid)},
        "metrics": {
            "balanced_accuracy": round(float(balanced_accuracy_score(y_valid, prediction)), 4),
            "f1": round(float(f1_score(y_valid, prediction, zero_division=0)), 4),
        },
        "details": detail,
        "boundary": recipe["explanation_rule"],
    }


def evaluate_algorithm_suite() -> dict[str, Any]:
    run_id = str(uuid4())
    started = time.perf_counter()
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO app.algorithm_evaluation_run (run_id, status, dataset_anchor)
            VALUES (:run_id, 'running', DATE '2025-12-29')
        """), {"run_id": run_id})
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '15000ms'"))
                recipes = [dict(row) for row in connection.execute(text("""
                    SELECT * FROM app.analysis_recipe WHERE status='published'
                      AND algorithm_name = ANY(:algorithms)
                """), {"algorithms": ALGORITHM_ORDER}).mappings()]
                if len(recipes) != 6:
                    raise ValueError(f"预期 6 个已发布算法 Recipe，实际 {len(recipes)} 个")
                recipe_map = {item["algorithm_name"]: item for item in recipes}
                production_rows = _execute_sql(connection, recipe_map["LinearRegression"]["feature_sql"])
                quality_rows = _execute_sql(connection, recipe_map["LogisticRegression"]["feature_sql"])
                kmeans_rows = _execute_sql(connection, recipe_map["KMeans"]["feature_sql"])
                isolation_rows = _execute_sql(connection, recipe_map["IsolationForest"]["feature_sql"])
            finally:
                transaction.rollback()

        results: list[dict[str, Any]] = []
        ordered = sorted(production_rows, key=lambda item: (item["business_date"], item["line_id"]))
        first_day = date.fromisoformat(ordered[0]["business_date"])
        train = [row for row in ordered if row["business_date"] <= "2025-11-30"]
        valid = [row for row in ordered if row["business_date"] >= "2025-12-01"]

        def regression_features(row: dict[str, Any]) -> list[float]:
            day_index = (date.fromisoformat(row["business_date"]) - first_day).days
            line_no = int(str(row["line_id"]).removeprefix("L"))
            return [float(row["planned_qty"]), float(line_no), float(day_index)]

        x_train = np.asarray([regression_features(row) for row in train], dtype=float)
        y_train = np.asarray([float(row["final_output"]) for row in train], dtype=float)
        x_valid = np.asarray([regression_features(row) for row in valid], dtype=float)
        y_valid = np.asarray([float(row["final_output"]) for row in valid], dtype=float)
        linear = LinearRegression().fit(x_train, y_train)
        prediction = linear.predict(x_valid)
        recipe = recipe_map["LinearRegression"]
        results.append({
            "algorithm": "LinearRegression", "recipe_code": recipe["recipe_code"], "scene": recipe["scene"],
            "use_case": "独立模型验收：计划与产线特征预测末工序完工量", "status": "passed",
            "split": {"method": "time_holdout", "training": "2025-10-01..2025-11-30", "validation": "2025-12-01..2025-12-29"},
            "rows": {"training": len(train), "validation": len(valid)},
            "metrics": {"mae": round(float(mean_absolute_error(y_valid, prediction)), 2), "r2": round(float(r2_score(y_valid, prediction)), 4)},
            "details": {"features": ["planned_qty", "line_no", "day_index"], "coefficients": [round(float(value), 4) for value in linear.coef_]},
            "boundary": "该结果是独立模型模板验收，与生产页七日趋势计算模式严格分离。",
        })
        for algorithm in ("LogisticRegression", "DecisionTree", "RandomForest"):
            results.append(_classification_result(algorithm, recipe_map[algorithm], quality_rows))

        recipe = recipe_map["KMeans"]
        features = list(recipe["feature_columns"])
        matrix = np.asarray([[float(row[name]) for name in features] for row in kmeans_rows], dtype=float)
        scaled = StandardScaler().fit_transform(matrix)
        params = dict(recipe["parameters"])
        kmeans = KMeans(n_clusters=int(params["n_clusters"]), n_init=int(params["n_init"]), random_state=int(params["random_state"])).fit(scaled)
        cluster_sizes = {str(label): int(np.sum(kmeans.labels_ == label)) for label in range(kmeans.n_clusters)}
        results.append({
            "algorithm": "KMeans", "recipe_code": recipe["recipe_code"], "scene": recipe["scene"],
            "use_case": recipe["recipe_name"], "status": "passed",
            "split": {"method": "unsupervised_full_window", "training": recipe["training_window"], "validation": "not_applicable"},
            "rows": {"training": len(kmeans_rows), "validation": 0},
            "metrics": {"silhouette": round(float(silhouette_score(scaled, kmeans.labels_)), 4)},
            "details": {"cluster_sizes": cluster_sizes}, "boundary": recipe["explanation_rule"],
        })

        recipe = recipe_map["IsolationForest"]
        features = list(recipe["feature_columns"])
        baseline = [row for row in isolation_rows if row["business_date"] <= "2025-11-30"]
        scoring = [row for row in isolation_rows if row["business_date"] >= "2025-12-01"]
        x_train = np.asarray([[float(row[name]) for name in features] for row in baseline], dtype=float)
        x_score = np.asarray([[float(row[name]) for name in features] for row in scoring], dtype=float)
        scaler = StandardScaler().fit(x_train)
        params = dict(recipe["parameters"])
        model = IsolationForest(
            n_estimators=int(params["n_estimators"]), contamination=float(params["contamination"]),
            random_state=int(params["random_state"]), n_jobs=1,
        ).fit(scaler.transform(x_train))
        labels = model.predict(scaler.transform(x_score))
        anomaly_count = int(np.sum(labels == -1))
        results.append({
            "algorithm": "IsolationForest", "recipe_code": recipe["recipe_code"], "scene": recipe["scene"],
            "use_case": recipe["recipe_name"], "status": "passed",
            "split": {"method": "baseline_scoring", "training": recipe["training_window"], "validation": recipe["scoring_window"]},
            "rows": {"training": len(baseline), "validation": len(scoring)},
            "metrics": {"anomaly_count": anomaly_count, "anomaly_rate": round(anomaly_count / len(scoring), 4)},
            "details": {"expected_top_entity": "由设备诊断工作流动态识别"}, "boundary": recipe["explanation_rule"],
        })
        results.sort(key=lambda item: ALGORITHM_ORDER.index(item["algorithm"]))
        duration_ms = max(1, round((time.perf_counter() - started) * 1000))
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE app.algorithm_evaluation_run SET status='completed', algorithm_count=:count,
                    results=CAST(:results AS jsonb), duration_ms=:duration_ms, completed_at=NOW()
                WHERE run_id=:run_id
            """), {"run_id": run_id, "count": len(results), "results": json.dumps(results, ensure_ascii=False), "duration_ms": duration_ms})
        return {
            "run_id": run_id, "status": "completed", "dataset_anchor": "2025-12-29",
            "algorithm_count": len(results), "passed_count": sum(item["status"] == "passed" for item in results),
            "duration_ms": duration_ms, "algorithms": results,
            "guardrail": "验收只执行审核 Recipe；指标用于证明工程链路可复现，不等同于生产部署承诺。",
        }
    except Exception as exc:
        duration_ms = max(1, round((time.perf_counter() - started) * 1000))
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE app.algorithm_evaluation_run SET status='failed', error_message=:error,
                    duration_ms=:duration_ms, completed_at=NOW() WHERE run_id=:run_id
            """), {"run_id": run_id, "error": str(exc)[:500], "duration_ms": duration_ms})
        raise
