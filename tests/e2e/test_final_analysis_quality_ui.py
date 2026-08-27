from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
LOCAL_TEST_PACKAGES = ROOT / ".tools" / "python"
LOCAL_GREENLET = LOCAL_TEST_PACKAGES / "greenlet" / (
    f"_greenlet.cp{sys.version_info.major}{sys.version_info.minor}-win_amd64.pyd"
)
if LOCAL_TEST_PACKAGES.is_dir() and LOCAL_GREENLET.is_file():
    sys.path.insert(0, str(LOCAL_TEST_PACKAGES))

from playwright.sync_api import expect, sync_playwright  # noqa: E402


BASE_URL = "http://localhost:8080"
ARTIFACTS = ROOT / "artifacts"


def evaluation_payload() -> dict:
    metric_specs = [
        ("rag_recall", "RAG 必需表召回", 100.0, "%", 95.0, "gte", True),
        ("sql_first_pass", "SQL 一次通过", 92.0, "%", 80.0, "gte", True),
        ("run_success", "问析成功率", 83.8, "%", 90.0, "gte", False),
        ("evidence_chain", "证据链完整率", 100.0, "%", 100.0, "gte", True),
        ("question_coverage", "标准问题覆盖", 85.0, "%", 80.0, "gte", True),
        ("p95_latency", "P95 问析延迟", 68400.0, "ms", 120000.0, "lte", True),
    ]
    metrics = [
        {"key": key, "label": label, "value": value, "unit": unit, "threshold": threshold,
         "direction": direction, "passed": passed, "description": f"{label}的固定评测说明"}
        for key, label, value, unit, threshold, direction, passed in metric_specs
    ]
    cases = [
        {"case_code": f"case-{index:02d}", "scene": "quality", "question": f"金标问题 {index}",
         "metric_ok": True, "expected_tables": ["demo.fact_quality_inspection"],
         "recalled_tables": ["demo.fact_quality_inspection"], "passed": True}
        for index in range(1, 7)
    ]
    return {
        "generated_at": "2026-08-26T20:00:00+08:00",
        "window": {"runs": 37, "limit": 50, "completed": 31, "failed": 6},
        "summary": {"passed_gates": 5, "total_gates": 6, "status": "ready"},
        "metrics": metrics,
        "rag": {"case_count": 6, "passed_cases": 6, "case_pass_pct": 100.0,
                "required_table_recall_pct": 100.0, "metric_accuracy_pct": 100.0,
                "top_k": 10, "cases": cases},
        "clarification": {"total": 5, "resolved": 4, "pending": 1, "resolution_pct": 80.0},
        "recent_runs": [{"run_id": "run-eval-001", "question": "本月各产线计划达成率", "scene": "production",
                         "status": "completed", "model_id": "deepseek-v4-pro", "duration_ms": 68400,
                         "repair_count": 0, "evidence_complete": True, "started_at": "2026-08-26T19:00:00+08:00"}],
        "methodology": "固定验证案例 + 最近 50 次真实运行；不调用 DeepSeek 生成评测分数。",
    }


def clarification_payload() -> dict:
    return {
        "status": "needs_clarification", "clarification_id": "6e076891-3b50-4586-a7a7-6f82c03607dc",
        "question": "分析一下设备", "detected_scene": "equipment",
        "missing_fields": ["metric", "time_range"],
        "prompt": "这个问题还缺少分析指标、时间范围。请选择一个完整问法，或在原问题中补充后再次提交。",
        "options": [
            {"label": "停机时长", "question": "本月各设备非计划停机时长排名"},
            {"label": "报警次数", "question": "本月各设备报警次数排名"},
            {"label": "停机趋势", "question": "最近30天设备停机时长趋势"},
        ],
        "trace": [{"node_name": "clarify", "display_name": "问题歧义澄清", "status": "waiting", "duration_ms": 1, "summary": "等待补充", "payload": {}}],
    }


def agent_payload() -> dict:
    rows = [
        {"equipment_name": "热处理炉8", "downtime_minutes": 1450},
        {"equipment_name": "数控车床1", "downtime_minutes": 820},
        {"equipment_name": "冲压机2", "downtime_minutes": 610},
    ]
    trace = [
        {"node_name": name, "display_name": title, "status": "completed", "duration_ms": 12, "summary": "节点执行完成", "payload": {}}
        for name, title in [
            ("clarify", "问题完整性检查"), ("retrieve", "混合 RAG 检索"), ("plan", "分析计划"),
            ("text_to_sql", "Text-to-SQL"), ("validate_sql", "SQL 安全校验"),
            ("execute_sql", "只读执行"), ("build_chart", "图表生成"), ("summarize", "结论生成"),
        ]
    ]
    return {
        "run_id": "export-run-001", "status": "completed", "question": "本月各设备非计划停机时长排名",
        "model": "deepseek-v4-pro", "generation_mode": "deepseek", "duration_ms": 8640,
        "time_range": {"start": "2025-12-01", "end": "2025-12-29", "anchor": "2025-12-29"},
        "plan": ["检索证据", "生成 SQL", "执行与解释"],
        "evidence": {"metric": {"code": "downtime_minutes", "name": "停机时长", "formula": "SUM(duration_minutes)", "version": "1.0"},
                     "rule": "只统计非计划停机", "rules": [], "tables": ["demo.fact_equipment_event", "demo.dim_equipment"],
                     "relations": [{"source_table": "demo.fact_equipment_event", "source_column": "equipment_id", "target_table": "demo.dim_equipment", "target_column": "equipment_id"}],
                     "items": [{"id": 1, "source_type": "business", "source_id": "metric:downtime_minutes", "title": "指标：停机时长", "score": 1.0, "channels": ["exact", "vector"]}],
                     "retrieval": {"strategy": "exact + fuzzy + vector / RRF", "top_k": 10, "channel_hits": {"exact": 8, "fuzzy": 10, "vector": 10}, "context_reduction_pct": 71.2}},
        "sql": {"text": "SELECT equipment_name, SUM(duration_minutes) AS downtime_minutes FROM demo.fact_equipment_event GROUP BY equipment_name LIMIT 100", "validation": "passed", "repair_count": 0, "referenced_tables": ["demo.fact_equipment_event"]},
        "result": {"columns": ["equipment_name", "downtime_minutes"], "rows": rows, "row_count": len(rows)},
        "chart": {"type": "bar", "title": "本月设备非计划停机时长排名", "x_field": "equipment_name", "y_field": "downtime_minutes", "unit": "分钟", "categories": [row["equipment_name"] for row in rows], "series": [{"name": "停机时长", "data": [row["downtime_minutes"] for row in rows]}]},
        "answer": "热处理炉8的非计划停机时长最高，建议优先核查相关事件记录。", "trace": trace,
    }


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        errors: list[str] = []
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)

        page.route("**/api/v1/agent/evaluation/overview", lambda route: route.fulfill(status=200, json=evaluation_payload()))
        page.route("**/api/v1/system/deepseek/config", lambda route: route.fulfill(status=200, json={
            "configured": True, "status": "configured", "source": "runtime", "model": "deepseek-v4-pro",
            "base_url": "https://api.deepseek.com", "reasoning_effort": "high", "runtime_only": True, "can_clear": True,
        }))

        def handle_agent(route) -> None:
            payload = route.request.post_data_json
            if payload["question"] == "分析一下设备":
                route.fulfill(status=200, json=clarification_payload())
                return
            assert payload["clarification_id"] == "6e076891-3b50-4586-a7a7-6f82c03607dc"
            route.fulfill(status=200, json=agent_payload())

        page.route("**/api/v1/agent/runs", handle_agent)
        page.goto(BASE_URL, wait_until="networkidle")

        page.get_by_role("button", name="问析评测 08").click()
        expect(page.locator(".evaluation-metrics article")).to_have_count(6)
        expect(page.locator(".evaluation-gate-dial strong")).to_have_text("5/6")
        expect(page.locator(".evaluation-case-list article")).to_have_count(6)
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        page.wait_for_timeout(900)
        expect(page.locator(".evaluation-view")).to_have_css("opacity", "1")
        page.screenshot(path=str(ARTIFACTS / "final-analysis-evaluation.png"), full_page=True, animations="disabled")

        page.get_by_role("button", name="智能问析 07").click()
        page.get_by_label("分析问题").fill("分析一下设备")
        page.get_by_role("button", name="启动智能问析 →").click()
        expect(page.locator(".clarification-card")).to_be_visible()
        expect(page.locator(".missing-field-list span")).to_have_count(2)
        page.wait_for_timeout(500)
        expect(page.locator(".agent-view")).to_have_css("opacity", "1")
        page.screenshot(path=str(ARTIFACTS / "final-clarification.png"), full_page=True, animations="disabled")
        page.locator(".clarification-options button").first.click()
        expect(page.locator(".result-section")).to_be_visible()

        with page.expect_download() as csv_info:
            page.get_by_role("button", name="CSV 结果表 ↓").click()
        csv_path = csv_info.value.path()
        assert csv_info.value.suggested_filename.endswith(".csv")
        assert csv_path is not None and Path(csv_path).read_bytes().startswith(b"\xef\xbb\xbf")

        with page.expect_download() as png_info:
            page.get_by_role("button", name="PNG 图表 ↓").click()
        png_path = png_info.value.path()
        assert png_info.value.suggested_filename.endswith(".png")
        assert png_path is not None and Path(png_path).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        expect(page.locator(".result-header-tools>small")).to_contain_text("PNG 已导出")
        page.wait_for_timeout(900)
        page.screenshot(path=str(ARTIFACTS / "final-clarification-and-export.png"), full_page=True, animations="disabled")

        assert not errors, errors
        browser.close()
    print("Final analysis quality UI test passed")


if __name__ == "__main__":
    main()
