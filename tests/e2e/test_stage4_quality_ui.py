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


ARTIFACTS = ROOT / "artifacts"
BASE_URL = "http://localhost:8080"


def run_quality_page(page, screenshot_name: str) -> dict:
    console_errors: list[str] = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.goto(BASE_URL, wait_until="networkidle")
    page.get_by_role("button", name="质量驾驶舱 04").click()
    expect(page.get_by_role("heading", name="质量，不止一个良率")).to_be_visible()
    expect(page.get_by_text("一键生成可演示的质量分析闭环")).to_be_visible()

    with page.expect_response(lambda response: response.url.endswith("/api/v1/agent/quality/brief") and response.request.method == "POST", timeout=180_000) as response_info:
        page.get_by_role("button", name="生成本月质量简报 ↗").click()
    response = response_info.value
    assert response.ok, response.status
    payload = response.json()

    expect(page.locator(".quality-kpis")).to_be_visible(timeout=30_000)
    expect(page.locator(".kpi-primary>strong")).to_contain_text("94.78")
    expect(page.locator(".kpi-primary>p")).to_contain_text("-1.19 pp")
    expect(page.locator(".quality-kpis article").nth(2).locator("strong")).to_have_text("热处理")
    expect(page.locator(".kpi-alert>strong")).to_have_text("尺寸偏差")
    expect(page.locator(".quality-pareto .pareto-item")).to_have_count(6)
    expect(page.locator(".quality-proof-grid .quality-proof")).to_have_count(2)
    expect(page.locator(".quality-proof:last-child article")).to_have_count(4)
    page.screenshot(path=str(ARTIFACTS / screenshot_name), full_page=True)
    assert not console_errors, console_errors
    return payload


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        desktop = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        run_quality_page(desktop, "stage4-quality-desktop.png")
        desktop.get_by_role("button", name="01 缺陷 Pareto →").click()
        expect(desktop.get_by_label("分析问题")).to_have_value("本月缺陷类型 Pareto 分析")
        browser.close()


if __name__ == "__main__":
    main()
