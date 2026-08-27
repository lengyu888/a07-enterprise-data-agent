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


def configured(route) -> None:
    route.fulfill(status=200, json={
        "configured": True, "status": "configured", "source": "runtime",
        "model": "deepseek-v4-pro", "base_url": "https://api.deepseek.com",
        "reasoning_effort": "high", "runtime_only": True, "can_clear": True,
    })


def run_payload(run_id: str, original: str, resolved: str, parent: str | None) -> dict:
    rows = [{"line_name": "一号柔性产线", "plan_attainment": 96.82}, {"line_name": "二号柔性产线", "plan_attainment": 93.89}]
    return {
        "run_id": run_id, "status": "completed", "scene": "production", "question": resolved,
        "model": "deepseek-v4-pro", "generation_mode": "deepseek", "duration_ms": 1820,
        "time_range": {"start": "2025-11-01" if "上月" in resolved else "2025-12-01", "end": "2025-11-30" if "上月" in resolved else "2025-12-29", "anchor": "2025-12-29"},
        "plan": ["检索指标口径", "按产线聚合", "生成结论"],
        "evidence": {
            "metric": {"code": "plan_attainment", "name": "计划达成率", "formula": "SUM(final_output)/SUM(planned_qty)", "version": "1.0"},
            "rule": "只统计末工序完工量", "rules": [],
            "tables": ["demo.fact_work_order", "demo.fact_process_output", "demo.dim_line"], "relations": [],
            "items": [{"id": 1, "source_type": "business", "source_id": "metric:plan_attainment", "title": "指标：计划达成率", "score": 1, "channels": ["exact", "fuzzy", "vector"]}],
            "retrieval": {"strategy": "hybrid_rrf", "top_k": 10, "channel_hits": {"exact": 3, "fuzzy": 5, "vector": 5}, "context_reduction_pct": 75},
        },
        "sql": {"text": "SELECT line_name, 96.82 AS plan_attainment FROM demo.dim_line LIMIT 100", "validation": "passed", "repair_count": 0, "referenced_tables": ["demo.dim_line"]},
        "result": {"columns": ["line_name", "plan_attainment"], "rows": rows, "row_count": 2},
        "chart": {"type": "bar", "title": "各产线计划达成率", "x_field": "line_name", "y_field": "plan_attainment", "unit": "%", "categories": [row["line_name"] for row in rows], "series": [{"name": "计划达成率", "data": [row["plan_attainment"] for row in rows]}]},
        "answer": "二号柔性产线计划达成率最低，建议下钻当期计划与末工序完工差额。",
        "trace": [{"node_name": name, "display_name": name, "status": "completed", "duration_ms": 10, "summary": "完成", "payload": {}} for name in ["contextualize", "retrieve", "plan", "text_to_sql", "validate_sql", "execute_sql", "build_chart", "summarize"]],
        "conversation": {"original_question": original, "resolved_question": resolved, "parent_run_id": parent, "retry_of_run_id": None, "suggestions": ["换成上月", "按产线展开", "查看最近30天趋势"]},
    }


def template_payload() -> list[dict]:
    specs = [
        ("quality_inspection", "质量检验记录", "质量分析", ["business_date", "order_no", "process_code", "inspected_qty", "qualified_qty", "inspector_group"]),
        ("equipment_event", "设备异常事件", "设备异常", ["equipment_code", "event_type", "event_code", "event_reason", "start_time", "end_time", "is_planned"]),
        ("production_output", "生产完工记录", "生产趋势", ["business_date", "order_no", "product_code", "line_code", "planned_qty", "completed_qty", "scrap_qty", "rework_qty", "shift_code"]),
    ]
    return [{"code": code, "name": name, "scene": scene, "description": "固定字段、整批校验、原子写入。", "target_tables": ["demo.fact"], "columns": columns, "sample_csv": ",".join(columns) + "\n" + ",".join(["sample"] * len(columns)) + "\n", "limits": {"max_rows": 500, "date_range": ["2025-11-01", "2025-12-29"]}} for code, name, scene, columns in specs]


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        console_errors: list[str] = []
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.route("**/api/v1/system/deepseek/config", configured)
        page.route("**/api/v1/data-imports/templates", lambda route: route.fulfill(status=200, json=template_payload()))
        page.route("**/api/v1/data-imports?limit=6", lambda route: route.fulfill(status=200, json=[]))

        imported: list[dict] = []

        def handle_import(route) -> None:
            if route.request.method == "POST":
                imported.append(route.request.post_data_json)
                route.fulfill(status=200, json={"batch_id": "117f0815-e433-4f33-bd14-8cbcdf836f2c", "status": "completed", "template_code": "quality_inspection", "template_name": "质量检验记录", "row_count": 1, "target_tables": ["demo.fact_quality_inspection"], "summary": {"accepted_rows": 1, "rejected_rows": 0, "date_range": ["2025-11-01", "2025-12-29"]}})
            else:
                route.fulfill(status=200, json=[])

        page.route("**/api/v1/data-imports", handle_import)
        agent_requests: list[dict] = []

        def handle_agent(route) -> None:
            payload = route.request.post_data_json
            agent_requests.append(payload)
            if payload["question"] == "换成上月":
                assert payload["parent_run_id"] == "11111111-1111-4111-8111-111111111111"
                route.fulfill(status=200, json=run_payload("22222222-2222-4222-8222-222222222222", "换成上月", "上月各产线计划达成率", payload["parent_run_id"]))
            else:
                route.fulfill(status=200, json=run_payload("11111111-1111-4111-8111-111111111111", payload["question"], payload["question"], None))

        page.route("**/api/v1/agent/runs", handle_agent)
        page.goto(BASE_URL, wait_until="networkidle")

        page.get_by_role("button", name="数据目录 02").click()
        page.get_by_role("button", name="导入业务数据").click()
        expect(page.locator(".data-import-panel")).to_be_visible()
        expect(page.locator(".import-layout > aside > button")).to_have_count(3)
        page.locator(".csv-drop input").set_input_files({"name": "quality.csv", "mimeType": "text/csv", "buffer": b"business_date,order_no,process_code,inspected_qty,qualified_qty,inspector_group\n2025-12-29,MO2512291,OP30,100,99,QA-A\n"})
        page.get_by_role("button", name="校验并导入 PostgreSQL ↗").click()
        expect(page.locator(".import-feedback.success")).to_contain_text("导入完成 · 1 行")
        assert imported and imported[0]["template_code"] == "quality_inspection"
        page.get_by_role("button", name="关闭导入窗口").click()

        page.get_by_role("button", name="智能问析 07").click()
        page.get_by_label("分析问题").fill("本月各产线计划达成率")
        page.get_by_role("button", name="启动智能问析 →").click()
        expect(page.locator(".answer-card")).to_be_visible()
        page.locator(".follow-up-suggestions button").filter(has_text="换成上月").click()
        expect(page.locator(".conversation-ledger")).to_be_visible()
        expect(page.locator(".conversation-ledger article")).to_have_count(2)
        expect(page.locator(".conversation-ledger")).to_contain_text("解析为：上月各产线计划达成率")
        assert len(agent_requests) == 2
        page.screenshot(path=str(ARTIFACTS / "phase7-context-and-import.png"), full_page=True, animations="disabled")
        assert not console_errors, console_errors
        browser.close()
    print("Phase 7 workflow UI test passed")


if __name__ == "__main__":
    main()
