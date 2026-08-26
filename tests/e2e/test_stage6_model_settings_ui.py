from __future__ import annotations

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
TEST_KEY = "sk-test-browser-runtime-only-123456"


def config_payload(configured: bool, model: str = "deepseek-v4-pro") -> dict:
    return {
        "configured": configured,
        "status": "configured" if configured else "not_configured",
        "source": "runtime" if configured else "none",
        "model": model,
        "base_url": "https://api.deepseek.com",
        "reasoning_effort": "high",
        "runtime_only": configured,
        "can_clear": configured,
        "verified": configured,
    }


def no_horizontal_overflow(page) -> bool:
    return page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    state = {"configured": False, "model": "deepseek-v4-pro", "put_count": 0}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        desktop = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        desktop.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )

        def handle_config(route) -> None:
            method = route.request.method
            if method == "PUT":
                request = json.loads(route.request.post_data or "{}")
                expected_key = TEST_KEY if state["put_count"] == 0 else None
                expected_model = "deepseek-v4-pro" if state["put_count"] == 0 else "deepseek-v4-flash"
                assert request == {"api_key": expected_key, "model": expected_model, "verify": True}
                state["put_count"] += 1
                state["configured"] = True
                state["model"] = request["model"]
            elif method == "DELETE":
                state["configured"] = False
                state["model"] = "deepseek-v4-pro"
            route.fulfill(status=200, json=config_payload(state["configured"], state["model"]))

        desktop.route("**/api/v1/system/deepseek/config", handle_config)
        desktop.goto(BASE_URL, wait_until="networkidle")
        desktop.get_by_role("button", name="模型配置 08").click()
        expect(desktop.get_by_role("heading", name="把模型连接 留在本机")).to_be_visible()
        expect(desktop.locator(".settings-hero aside strong")).to_have_text("SETUP")
        expect(desktop.locator(".connection-card dd").first).to_have_text("尚未配置")

        key_input = desktop.get_by_label("DeepSeek API Key")
        expect(key_input).to_have_attribute("type", "password")
        key_input.fill(TEST_KEY)
        desktop.get_by_role("button", name="显示").click()
        expect(key_input).to_have_attribute("type", "text")
        desktop.get_by_role("button", name="保存并验证连接 →").click()
        expect(desktop.get_by_text("连接验证通过，当前 Agent 已切换至 deepseek-v4-pro。")).to_be_visible()
        expect(desktop.locator(".settings-hero aside strong")).to_have_text("READY")
        expect(desktop.locator(".connection-card dd").first).to_have_text("前端运行时配置")
        expect(key_input).to_have_value("")
        expect(key_input).to_have_attribute("type", "password")
        assert TEST_KEY not in desktop.locator("body").inner_text()

        desktop.locator('input[name="deepseek-model"][value="deepseek-v4-flash"]').check(force=True)
        desktop.get_by_role("button", name="保存并验证连接 →").click()
        expect(desktop.get_by_text("连接验证通过，当前 Agent 已切换至 deepseek-v4-flash。")).to_be_visible()
        expect(desktop.locator(".connection-card dd").nth(1)).to_have_text("deepseek-v4-flash")
        assert no_horizontal_overflow(desktop)
        desktop.screenshot(
            path=str(ARTIFACTS / "stage6-model-settings-desktop.png"), full_page=True
        )

        desktop.get_by_role("button", name="清除页面配置").click()
        expect(desktop.locator(".settings-hero aside strong")).to_have_text("SETUP")
        expect(desktop.get_by_text("页面临时 Key 已安全清除。")).to_be_visible()

        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    main()
