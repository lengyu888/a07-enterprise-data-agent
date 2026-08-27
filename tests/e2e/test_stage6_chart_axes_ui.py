from __future__ import annotations

from copy import deepcopy
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


def agent_run(chart_type: str) -> dict:
    is_line = chart_type == "line"
    categories = (
        ["2025-12-01", "2025-12-06", "2025-12-11", "2025-12-16", "2025-12-21", "2025-12-26", "2025-12-29"]
        if is_line
        else ["数控车床-01", "冲压机-02", "装配机器人-03"]
    )
    values = [2480, 2525, 2570, 2630, 2675, 2710, 2734] if is_line else [23, 16, 9]
    x_field = "business_date" if is_line else "equipment_name"
    y_field = "final_output" if is_line else "alarm_count"
    unit = "件" if is_line else "次"
    rows = [
        {x_field: category, y_field: value}
        for category, value in zip(categories, values, strict=True)
    ]
    return {
        "run_id": f"axis-{chart_type}",
        "status": "completed",
        "scene": "production" if is_line else "equipment",
        "question": "验证生成图表坐标轴",
        "model": "deepseek-chat",
        "generation_mode": "test_fixture",
        "duration_ms": 832,
        "time_range": {"start": "2025-12-01", "end": "2025-12-29", "anchor": "2025-12-29"},
        "plan": ["检索口径", "生成 SQL", "执行查询", "生成图表"],
        "evidence": {
            "metric": {
                "code": y_field,
                "name": "完工产量" if is_line else "报警次数",
                "formula": "SUM(final_output)" if is_line else "COUNT(*) FILTER (WHERE event_type = 'alarm')",
                "version": "1.0",
            },
            "rule": "所有统计均使用已发布口径，并保留可追溯的时间范围和数据表。",
            "rules": [],
            "tables": ["demo.fact_production_daily" if is_line else "demo.fact_equipment_event"],
            "relations": [],
            "items": [
                {
                    "id": 1,
                    "source_type": "BUSINESS",
                    "source_id": "metric-1",
                    "title": "指标：完工产量" if is_line else "指标：报警次数",
                    "score": 0.98,
                    "channels": ["exact", "fuzzy", "vector"],
                }
            ],
            "retrieval": {
                "strategy": "hybrid",
                "top_k": 6,
                "channel_hits": {"exact": 1, "fuzzy": 1, "vector": 1},
                "context_reduction_pct": 72,
            },
        },
        "sql": {
            "text": f"SELECT {x_field}, SUM({y_field}) AS {y_field} FROM demo.sample GROUP BY {x_field} LIMIT 100",
            "validation": "passed",
            "repair_count": 0,
            "referenced_tables": ["demo.sample"],
        },
        "result": {"columns": [x_field, y_field], "rows": rows, "row_count": len(rows)},
        "chart": {
            "type": chart_type,
            "title": "每日完工产量趋势" if is_line else "设备报警次数排名",
            "x_field": x_field,
            "y_field": y_field,
            "unit": unit,
            "categories": categories,
            "series": [{"name": y_field, "data": values}],
        },
        "answer": "图表已基于真实查询结果生成，并明确标注横轴、纵轴、单位与刻度。",
        "conversation": {"original_question": "验证生成图表坐标轴", "resolved_question": "验证生成图表坐标轴", "parent_run_id": None, "retry_of_run_id": None, "suggestions": ["换成上月", "按产线展开", "查看最近30天趋势"]},
        "trace": [
            {
                "node_name": f"node_{index}",
                "display_name": name,
                "status": "completed",
                "duration_ms": 80 + index,
                "summary": f"{name}完成",
                "payload": {},
            }
            for index, name in enumerate(["意图识别", "证据检索", "SQL 生成", "SQL 校验", "查询执行", "图表生成", "结论生成"])
        ],
    }


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    responses = [agent_run("bar"), agent_run("line")]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )

        def fulfill_agent_run(route) -> None:
            route.fulfill(status=200, json=deepcopy(responses.pop(0)))

        page.route(
            "**/api/v1/system/deepseek/config",
            lambda route: route.fulfill(
                status=200,
                json={
                    "configured": True,
                    "status": "configured",
                    "source": "runtime",
                    "model": "deepseek-v4-pro",
                    "base_url": "https://api.deepseek.com",
                    "reasoning_effort": "high",
                    "runtime_only": True,
                    "can_clear": True,
                },
            ),
        )
        page.route("**/api/v1/agent/runs", fulfill_agent_run)
        page.goto(BASE_URL, wait_until="networkidle")
        page.get_by_role("button", name="智能问析 07").click()

        page.get_by_role("button", name="启动智能问析 →").click()
        expect(page.get_by_role("heading", name="设备报警次数排名")).to_be_visible()
        chart = page.locator(".yield-chart")
        expect(chart.locator(".chart-y-title")).to_have_text("报警次数（次）")
        expect(chart.locator(".chart-x-title")).to_have_text("设备")
        expect(chart.locator(".chart-scale span")).to_have_count(3)
        expect(chart.locator(".plot-axis-y")).to_be_visible()
        expect(chart.locator(".plot-axis-x")).to_be_visible()
        expect(chart.locator(".bar-column")).to_have_count(3)

        sql_font_size = float(
            page.locator(".sql-card pre").evaluate("element => getComputedStyle(element).fontSize").removesuffix("px")
        )
        source_font_size = float(
            page.locator(".source-proof>span").first.evaluate("element => getComputedStyle(element).fontSize").removesuffix("px")
        )
        assert sql_font_size >= 13
        assert source_font_size >= 11.5
        page.screenshot(path=str(ARTIFACTS / "stage6-chart-axes-bar.png"), full_page=True)

        page.get_by_role("button", name="启动智能问析 →").click()
        expect(page.get_by_role("heading", name="每日完工产量趋势")).to_be_visible()
        expect(chart.locator(".chart-y-title")).to_have_text("完工产量（件）")
        expect(chart.locator(".chart-x-title")).to_have_text("日期")
        expect(chart.locator(".chart-scale span")).to_have_count(3)
        expect(chart.locator(".line-plot .axis-line")).to_have_count(2)
        page.screenshot(path=str(ARTIFACTS / "stage6-chart-axes-line.png"), full_page=True)

        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    main()
