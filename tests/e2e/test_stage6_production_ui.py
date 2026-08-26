from __future__ import annotations

from datetime import date, timedelta
import json
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


def production_payload() -> dict:
    ranking = [
        {"line_id": "L03", "line_name": "三号装配产线", "final_output": 25075, "planned_qty": 25895, "plan_attainment": 96.83, "slope_per_day": -11.39, "direction": "下降"},
        {"line_id": "L01", "line_name": "一号柔性产线", "final_output": 25286, "planned_qty": 26117, "plan_attainment": 96.82, "slope_per_day": -9.75, "direction": "下降"},
        {"line_id": "L02", "line_name": "二号柔性产线", "final_output": 24174, "planned_qty": 25746, "plan_attainment": 93.89, "slope_per_day": -44.61, "direction": "下降"},
    ]
    start = date(2025, 12, 1)
    daily = [
        {"business_date": (start + timedelta(days=index)).isoformat(), "final_output": 2580 + (index % 5) * 34 - index * 3, "planned_qty": 2720, "plan_attainment": 95.2}
        for index in range(29)
    ]
    trace_names = [
        ("load_recipe", "RAG 与生产 Recipe"),
        ("execute_text_to_sql", "Text-to-SQL 安全执行"),
        ("fit_seven_day_trend", "七日线性趋势"),
        ("assess_plan_attainment", "生产达成评估"),
        ("compose_production_brief", "DeepSeek 生产简报"),
    ]
    return {
        "run_id": "stage6-ui-fixed-run", "status": "completed", "duration_ms": 1680,
        "period": {"start": "2025-12-01", "end": "2025-12-29", "anchor": "2025-12-29", "trend_window": "2025-12-23..2025-12-29"},
        "recipe": {"code": "production-7d-linear-trend-v1", "name": "产线七日完工趋势斜率", "algorithm": "LinearRegression", "version": "1.0", "features": ["final_output", "planned_qty", "plan_attainment"], "parameters": {"fit_days": 7, "random_state": 42, "mode": "trend_calculation"}, "feature_sql": "SELECT business_date, line_name, final_output FROM reviewed_production_recipe", "explanation_rule": "只以最近七个业务日拟合线性斜率，用于描述短期方向；不宣称具有产量预测能力。"},
        "assessment": {"final_output": 74535, "planned_qty": 77758, "plan_attainment": 95.86, "best_line": ranking[0], "attention_line": ranking[2], "rising_lines": 0, "declining_lines": 3, "status": "attention", "trend_disclaimer": "七日斜率仅描述短期方向，不是未来产量预测。"},
        "ranking": ranking,
        "daily_trend": daily,
        "line_trends": [],
        "brief": {"headline": "整体生产达成稳定，二号线需优先关注", "summary": "本月末工序完工 74535 件，整体计划达成率 95.86%。二号柔性产线达成率最低，最近七日呈下降方向。", "observations": ["三号装配产线达成率最高", "二号柔性产线与其他产线存在达成差距"], "actions": ["按日期下钻二号线计划与实际差异", "结合设备、质量记录进一步核查"], "generation_mode": "deepseek"},
        "evidence": {"metrics": [{"code": "final_output", "name": "完工产量", "formula": "SUM(completed_qty) FILTER (WHERE is_final_process=true)", "version": "1.0"}, {"code": "plan_attainment", "name": "计划达成率", "formula": "SUM(final_output)/SUM(planned_qty)", "version": "1.0"}], "tables": ["demo.fact_process_output", "demo.fact_work_order", "demo.dim_line"], "rules": ["只统计末工序"], "sources": ["完工产量"], "retrieval": [{"strategy": "hybrid_rrf", "context_reduction_pct": 84.0}]},
        "trace": [{"node_name": node, "display_name": name, "status": "completed", "duration_ms": 12 + index, "summary": f"{name}执行完成", "payload": {}} for index, (node, name) in enumerate(trace_names)],
    }


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    payload = production_payload()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        errors: list[str] = []
        desktop = browser.new_page(viewport={"width": 1440, "height": 1000})
        desktop.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        desktop.route("**/api/v1/agent/production/trend", lambda route: route.fulfill(
            status=200, content_type="application/json; charset=utf-8", body=json.dumps(payload, ensure_ascii=False)
        ))
        desktop.goto(BASE_URL, wait_until="networkidle")
        desktop.get_by_role("button", name="生产趋势 06").click()
        expect(desktop.get_by_role("heading", name="看清达成， 盯住趋势")).to_be_visible()
        expect(desktop.get_by_text("一次运行，回答“完成多少、差在哪里、方向怎样”")).to_be_visible()
        desktop.locator(".production-run").click()
        expect(desktop.locator(".production-kpis")).to_be_visible()
        expect(desktop.locator(".production-kpis")).to_contain_text("74,535")
        expect(desktop.locator(".production-kpis")).to_contain_text("95.86")
        expect(desktop.locator(".line-rank article")).to_have_count(3)
        expect(desktop.locator(".production-chart circle")).to_have_count(29)
        expect(desktop.locator(".production-chart .chart-y-title")).to_have_text("完工产量（件）")
        expect(desktop.locator(".production-chart .chart-y-ticks span")).to_have_count(3)
        expect(desktop.locator(".production-chart .chart-x-title")).to_have_text("业务日期（月-日）")
        expect(desktop.locator(".slope-section article")).to_have_count(3)
        expect(desktop.locator(".production-trace>div")).to_have_count(5)
        expect(desktop.locator(".production-brief")).to_contain_text("二号线需优先关注")

        with desktop.expect_response(lambda response: response.url.endswith("/api/v1/agent/algorithms/evaluate") and response.request.method == "POST", timeout=60_000) as response_info:
            desktop.locator(".algorithm-lab>header button").click()
        suite_response = response_info.value
        assert suite_response.ok, suite_response.status
        suite_payload = suite_response.json()
        expect(desktop.locator(".algorithm-grid article")).to_have_count(6)
        expect(desktop.locator(".algorithm-lab>footer")).to_contain_text("6/6 RECIPES PASSED")
        desktop.screenshot(path=str(ARTIFACTS / "stage6-production-desktop.png"), full_page=True)
        assert desktop.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        assert not errors, errors

        mobile_errors: list[str] = []
        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile.on("console", lambda message: mobile_errors.append(message.text) if message.type == "error" else None)
        mobile.route("**/api/v1/agent/production/trend", lambda route: route.fulfill(
            status=200, content_type="application/json; charset=utf-8", body=json.dumps(payload, ensure_ascii=False)
        ))
        mobile.route("**/api/v1/agent/algorithms/evaluate", lambda route: route.fulfill(
            status=200, content_type="application/json; charset=utf-8", body=json.dumps(suite_payload, ensure_ascii=False)
        ))
        mobile.goto(BASE_URL, wait_until="networkidle")
        mobile.locator(".view-nav button").nth(5).click()
        mobile.locator(".production-run").click()
        mobile.locator(".algorithm-lab>header button").click()
        expect(mobile.locator(".production-kpis")).to_be_visible()
        expect(mobile.locator(".algorithm-grid article")).to_have_count(6)
        expect(mobile.locator(".production-chart .chart-y-title")).to_be_visible()
        assert mobile.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        mobile.screenshot(path=str(ARTIFACTS / "stage6-production-mobile.png"), full_page=True)
        assert not mobile_errors, mobile_errors
        browser.close()


if __name__ == "__main__":
    main()
