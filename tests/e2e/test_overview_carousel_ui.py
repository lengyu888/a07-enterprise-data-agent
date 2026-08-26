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


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.goto(BASE_URL, wait_until="networkidle")

        carousel = page.locator(".overview-carousel")
        rail = carousel.locator(".overview-module-rail")
        expect(rail.locator("button")).to_have_count(7)
        expect(rail.locator("button.active")).to_contain_text("数据目录")
        expect(carousel.locator(".overview-slide h2")).to_contain_text("让数据资产")

        page.wait_for_timeout(6_800)
        expect(rail.locator("button.active")).to_contain_text("业务知识")
        expect(carousel.locator(".overview-slide h2")).to_contain_text("把业务口径")

        carousel.hover()
        paused_module = rail.locator("button.active").inner_text()
        page.wait_for_timeout(6_800)
        assert rail.locator("button.active").inner_text() == paused_module

        rail.get_by_role("button", name="06 生产趋势").click()
        expect(carousel.locator(".overview-slide h2")).to_contain_text("把计划差距")
        expect(carousel.get_by_role("button", name="打开生产趋势 →")).to_be_visible()
        page.wait_for_timeout(350)
        assert carousel.evaluate("element => getComputedStyle(element).opacity") == "1"
        assert page.locator(".overview-view").evaluate(
            "element => getComputedStyle(element).opacity"
        ) == "1"
        page.screenshot(
            path=str(ARTIFACTS / "overview-module-carousel.png"),
            full_page=True,
            animations="disabled",
        )

        carousel.get_by_role("button", name="打开生产趋势 →").click()
        expect(page.get_by_role("heading", name="看清达成， 盯住趋势")).to_be_visible()

        assert not errors, errors
        page.close()
        browser.close()


if __name__ == "__main__":
    main()
