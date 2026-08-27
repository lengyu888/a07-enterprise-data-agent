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
from test_phase7_workflow_ui import configured, run_payload  # noqa: E402


BASE_URL = "http://localhost:8080"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)

        retry_page = browser.new_page(viewport={"width": 1440, "height": 900})
        retry_page.route("**/api/v1/system/deepseek/config", configured)
        attempts: list[dict] = []

        def retry_handler(route) -> None:
            payload = route.request.post_data_json
            attempts.append(payload)
            if len(attempts) == 1:
                route.fulfill(status=502, json={"detail": {"message": "模拟上游瞬时失败", "run_id": payload["request_id"]}})
            else:
                route.fulfill(status=200, json=run_payload(
                    "33333333-3333-4333-8333-333333333333", payload["question"], payload["question"], None,
                ))

        retry_page.route("**/api/v1/agent/runs", retry_handler)
        retry_page.goto(BASE_URL, wait_until="networkidle")
        retry_page.get_by_role("button", name="智能问析 07").click()
        retry_page.get_by_label("分析问题").fill("本月各产线计划达成率")
        retry_page.get_by_role("button", name="启动智能问析 →").click()
        expect(retry_page.locator(".agent-error")).to_contain_text("模拟上游瞬时失败")
        retry_page.get_by_role("button", name="按原参数重试").click()
        expect(retry_page.locator(".answer-card")).to_be_visible()
        assert len(attempts) == 2
        assert attempts[1]["request_id"] != attempts[0]["request_id"]
        assert attempts[1]["retry_of_run_id"] == attempts[0]["request_id"]
        retry_page.close()

        cancel_page = browser.new_page(viewport={"width": 1440, "height": 900})
        cancel_page.route("**/api/v1/system/deepseek/config", configured)
        held_routes = []
        cancelled_ids: list[str] = []

        def hold_run(route) -> None:
            held_routes.append(route)

        def accept_cancel(route) -> None:
            cancelled_ids.append(route.request.url.rsplit("/", 2)[-2])
            route.fulfill(status=200, json={"run_id": cancelled_ids[-1], "status": "cancellation_requested", "accepted": True})

        cancel_page.route("**/api/v1/agent/runs", hold_run)
        cancel_page.route("**/api/v1/agent/runs/*/cancel", accept_cancel)
        cancel_page.goto(BASE_URL, wait_until="networkidle")
        cancel_page.get_by_role("button", name="智能问析 07").click()
        cancel_page.get_by_label("分析问题").fill("本月各产线计划达成率")
        cancel_page.get_by_role("button", name="启动智能问析 →").click()
        expect(cancel_page.get_by_role("button", name="取消本次运行")).to_be_visible()
        cancel_page.get_by_role("button", name="取消本次运行").click()
        expect(cancel_page.locator(".agent-error")).to_contain_text("本次运行已取消")
        assert len(held_routes) == 1
        assert len(cancelled_ids) == 1
        held_routes[0].abort()
        cancel_page.close()

        browser.close()
    print("Phase 7 run control UI test passed")


if __name__ == "__main__":
    main()
