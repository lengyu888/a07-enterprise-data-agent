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


def no_horizontal_overflow(page) -> bool:
    return page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)

        errors: list[str] = []
        desktop = browser.new_page(viewport={"width": 1440, "height": 1000})
        desktop.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        desktop.goto(BASE_URL, wait_until="networkidle")
        expect(desktop.get_by_role("heading", name="把计划差距 变成行动线索")).to_be_visible()
        body_font = desktop.locator("body").evaluate(
            "element => getComputedStyle(element).fontFamily"
        )
        section_code_size = float(
            desktop.locator(".section-code").first
            .evaluate("element => getComputedStyle(element).fontSize")
            .removesuffix("px")
        )
        hero_size = float(
            desktop.locator(".hero-copy h2")
            .evaluate("element => getComputedStyle(element).fontSize")
            .removesuffix("px")
        )
        assert "MiSans" in body_font
        assert section_code_size >= 11.5
        assert hero_size <= 80
        assert no_horizontal_overflow(desktop)
        desktop.wait_for_timeout(500)
        desktop.screenshot(
            path=str(ARTIFACTS / "stage6-polish-overview-desktop.png"), full_page=True
        )

        pages = [
            ("数据目录 02", ".catalog-view h2", "数据资源目录"),
            ("业务知识 03", ".knowledge-view h2", "业务知识管理"),
            ("质量驾驶舱 04", ".quality-hero h2", "良率"),
            ("设备诊断 05", ".equipment-hero h2", "先看偏离"),
            ("生产趋势 06", ".production-hero h2", "盯住趋势"),
            ("智能问析 07", ".agent-hero h2", "走完分析链路"),
        ]
        for button_name, selector, text in pages:
            desktop.get_by_role("button", name=button_name).click()
            expect(desktop.locator(selector)).to_contain_text(text)
            assert no_horizontal_overflow(desktop)
        desktop.wait_for_timeout(500)
        desktop.screenshot(
            path=str(ARTIFACTS / "stage6-polish-agent-desktop.png"), full_page=True
        )
        assert not errors, errors

        mobile_errors: list[str] = []
        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile.on(
            "console",
            lambda message: mobile_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        mobile.goto(BASE_URL, wait_until="networkidle")
        mobile_hero_size = float(
            mobile.locator(".hero-copy h2")
            .evaluate("element => getComputedStyle(element).fontSize")
            .removesuffix("px")
        )
        assert mobile_hero_size <= 52
        assert no_horizontal_overflow(mobile)
        mobile.wait_for_timeout(500)
        mobile.screenshot(
            path=str(ARTIFACTS / "stage6-polish-overview-mobile.png"), full_page=True
        )
        assert not mobile_errors, mobile_errors
        browser.close()


if __name__ == "__main__":
    main()
