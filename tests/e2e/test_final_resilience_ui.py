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


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)

        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.route(
            "**/api/v1/system/deepseek/config",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=(
                    '{"configured":false,"status":"not_configured","source":"none",'
                    '"model":"deepseek-v4-pro","base_url":"https://api.deepseek.com",'
                    '"reasoning_effort":"high","runtime_only":false,"can_clear":false}'
                ),
            ),
        )
        response = page.goto(BASE_URL, wait_until="networkidle")
        assert response is not None
        headers = response.headers
        assert headers["cache-control"] == "no-store"
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        expect(page.locator(".system-pill")).to_contain_text("MODEL REQUIRED")

        agent_posts = 0

        def count_agent_posts(request) -> None:
            nonlocal agent_posts
            if request.method == "POST" and request.url.endswith("/api/v1/agent/runs"):
                agent_posts += 1

        page.on("request", count_agent_posts)
        page.get_by_role("button", name="智能问析 07").click()
        page.get_by_role("button", name="启动智能问析").click()
        expect(page.locator(".agent-error")).to_contain_text("DeepSeek 尚未配置")
        expect(page.get_by_role("button", name="前往模型配置")).to_be_visible()
        # Questions now reach the backend clarification gate first; only a
        # complete question proceeds far enough to return the model-config error.
        assert agent_posts == 1
        page.close()

        timeout_page = browser.new_page(viewport={"width": 1440, "height": 900})

        def configured(route) -> None:
            if route.request.method == "GET":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=(
                        '{"configured":true,"status":"configured","source":"runtime",'
                        '"model":"deepseek-v4-pro","base_url":"https://api.deepseek.com",'
                        '"reasoning_effort":"high","runtime_only":true,"can_clear":true}'
                    ),
                )
            else:
                route.continue_()

        timeout_page.route("**/api/v1/system/deepseek/config", configured)
        timeout_page.route(
            "**/api/v1/agent/runs",
            lambda route: route.fulfill(
                status=504,
                content_type="application/json",
                body='{"detail":"upstream timeout"}',
            ),
        )
        timeout_page.goto(BASE_URL, wait_until="networkidle")
        timeout_page.get_by_role("button", name="智能问析 07").click()
        timeout_page.get_by_role("button", name="启动智能问析").click()
        expect(timeout_page.locator(".agent-error")).to_contain_text(
            "模型请求超时，请稍后重试或切换 V4 Flash"
        )
        timeout_page.close()

        metric_page = browser.new_page(viewport={"width": 1440, "height": 900})
        metric_page.goto(BASE_URL, wait_until="networkidle")
        metric_page.get_by_role("button", name="业务知识 03").click()

        def reject_metric_update(route) -> None:
            if route.request.method == "PUT":
                route.fulfill(
                    status=409,
                    content_type="application/json",
                    body='{"detail":"指标编码已存在，请使用其他编码"}',
                )
            else:
                route.continue_()

        metric_page.route("**/api/v1/knowledge/metrics/*", reject_metric_update)
        metric_page.locator(".metric-list article").first.click()
        metric_page.get_by_role("button", name="保存口径").click()
        expect(metric_page.locator(".metric-editor .config-feedback.error")).to_contain_text(
            "指标编码已存在"
        )
        expect(metric_page.locator(".metric-editor")).to_be_visible()
        metric_page.close()

        browser.close()


if __name__ == "__main__":
    main()
