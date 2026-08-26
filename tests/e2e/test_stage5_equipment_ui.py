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


def run_equipment_page(page) -> dict:
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.goto(BASE_URL, wait_until="networkidle")
    page.get_by_role("button", name="设备诊断 05").click()
    expect(page.get_by_role("heading", name="别等停机， 先看偏离")).to_be_visible()
    expect(page.get_by_text("一次运行，展示从特征到解释的完整算法证据")).to_be_visible()
    with page.expect_response(lambda response: response.url.endswith("/api/v1/agent/equipment/diagnosis") and response.request.method == "POST", timeout=180_000) as response_info:
        page.get_by_role("button", name="运行设备异常诊断 ↗").click()
    response = response_info.value
    assert response.ok, response.status
    payload = response.json()
    expect(page.locator(".equipment-alert-band")).to_be_visible(timeout=30_000)
    expect(page.locator(".alert-identity>strong")).to_have_text("E08")
    expect(page.locator(".alert-identity>h3")).to_have_text("热处理炉8")
    expect(page.locator(".fleet-list article")).to_have_count(9)
    expect(page.locator(".deviation-grid article")).to_have_count(5)
    expect(page.locator(".equipment-trace>div")).to_have_count(5)
    expect(page.locator(".signal-chart circle")).to_have_count(payload["assessment"]["top_equipment"]["anomaly_days"])
    expect(page.locator(".equipment-brief")).to_contain_text("145")
    page.screenshot(path=str(ARTIFACTS / "stage5-equipment-desktop.png"), full_page=True)
    assert not errors, errors
    return payload


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        desktop = browser.new_page(viewport={"width": 1440, "height": 900})
        run_equipment_page(desktop)
        desktop.get_by_role("button", name="01 报警频次 →").click()
        expect(desktop.get_by_label("分析问题")).to_have_value("本月各设备报警次数排名")
        browser.close()


if __name__ == "__main__":
    main()
