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


def no_page_overflow(page) -> bool:
    return page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)

        errors: list[str] = []
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on(
            "console",
            lambda message: errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.goto(BASE_URL, wait_until="networkidle")
        expect(page.locator(".shell")).to_be_visible()
        expect(page.locator(".desktop-only-gate")).to_be_hidden()
        expect(page.locator(".view-nav button")).to_have_count(8)
        assert page.locator(".view-nav").evaluate(
            "element => element.scrollWidth <= element.clientWidth"
        )
        assert no_page_overflow(page)

        for button_name in [
            "数据目录 02",
            "业务知识 03",
            "质量驾驶舱 04",
            "设备诊断 05",
            "生产趋势 06",
            "智能问析 07",
            "模型配置 08",
        ]:
            page.get_by_role("button", name=button_name).click()
            assert no_page_overflow(page)

        expect(page.locator(".model-options label")).to_have_count(2)
        page.screenshot(
            path=str(ARTIFACTS / "desktop-workspace-1440x900.png"),
            full_page=True,
        )
        assert not errors, errors
        page.close()

        compact = browser.new_page(viewport={"width": 1024, "height": 768})
        compact.goto(BASE_URL, wait_until="networkidle")
        expect(compact.locator(".shell")).to_be_hidden()
        expect(compact.locator(".desktop-only-gate")).to_be_visible()
        expect(compact.get_by_text("请使用电脑浏览器打开分析工作台")).to_be_visible()
        expect(compact.get_by_text("RECOMMENDED DESKTOP · 1440 × 900")).to_be_visible()
        compact.screenshot(
            path=str(ARTIFACTS / "desktop-only-width-gate.png"), full_page=True
        )

        browser.close()


if __name__ == "__main__":
    main()
