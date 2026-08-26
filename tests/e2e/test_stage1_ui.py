from pathlib import Path
import sys


LOCAL_TEST_PACKAGES = Path(__file__).resolve().parents[2] / ".tools" / "python"
if LOCAL_TEST_PACKAGES.is_dir():
    sys.path.insert(0, str(LOCAL_TEST_PACKAGES))

from playwright.sync_api import sync_playwright  # noqa: E402


BASE_URL = "http://localhost:8080"
ARTIFACT_DIR = Path("artifacts")


def main() -> None:
    ARTIFACT_DIR.mkdir(exist_ok=True)
    console_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")

        assert page.get_by_text("phase-1", exact=True).is_visible()
        assert page.get_by_text("118,009", exact=True).is_visible()
        assert page.get_by_text("2025-12-29", exact=True).is_visible()
        page.wait_for_timeout(550)
        page.screenshot(path=ARTIFACT_DIR / "stage1-overview-desktop.png", full_page=True)

        page.locator(".view-nav button").nth(1).click()
        assert page.get_by_role("heading", name="数据资源目录").is_visible()
        assert page.locator(".table-list button").count() == 10
        page.get_by_role("button", name="质量分析 质量检验").click()
        page.get_by_text("qualified_qty", exact=True).wait_for()
        assert page.get_by_text("真实关系图", exact=True).is_visible()
        assert page.locator(".relation-canvas svg").is_visible()
        page.mouse.move(0, 0)
        page.wait_for_timeout(550)
        page.screenshot(path=ARTIFACT_DIR / "stage1-catalog-desktop.png", full_page=True)

        page.locator(".view-nav button").nth(2).click()
        assert page.get_by_role("heading", name="业务知识管理").is_visible()
        assert page.locator(".metric-list article").count() == 5
        page.get_by_role("heading", name="良率 %", exact=True).click()
        assert page.get_by_role("heading", name="编辑指标口径").is_visible()
        page.get_by_role("button", name="取消").click()
        page.mouse.move(0, 0)
        page.wait_for_timeout(550)
        page.screenshot(path=ARTIFACT_DIR / "stage1-knowledge-desktop.png", full_page=True)

        browser.close()

    assert not console_errors, f"Browser console errors: {console_errors}"
    print("Stage 1 browser test passed")


if __name__ == "__main__":
    main()
