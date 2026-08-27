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
        page.get_by_role("button", name="智能问析 07").click()

        assert page.get_by_role("heading", name="一句话，走完分析链路").is_visible()
        assert page.get_by_label("分析问题").input_value() == "分析本月各工序良率，找出良率最低的工序"
        page.screenshot(path=ARTIFACT_DIR / "stage2-agent-ready-desktop.png", full_page=True)

        page.get_by_role("button", name="启动智能问析 →").click()
        assert page.get_by_text("DeepSeek 正在推理并生成 SQL").is_visible()
        page.get_by_text("8 STEPS COMPLETED", exact=True).wait_for(timeout=180_000)

        assert page.locator(".trace-rail article").count() == 8
        assert page.get_by_text("SQLGLOT PASSED", exact=True).is_visible()
        assert page.locator(".yield-chart .bar-column").count() == 3
        assert page.get_by_text("热处理", exact=True).count() >= 2
        assert page.get_by_text("AGENT CONCLUSION", exact=True).is_visible()
        assert page.locator(".agent-error").count() == 0
        page.wait_for_timeout(900)
        page.screenshot(path=ARTIFACT_DIR / "stage2-agent-result-desktop.png", full_page=True)

        browser.close()

    assert not console_errors, f"Browser console errors: {console_errors}"
    print("Stage 2 browser test passed")


if __name__ == "__main__":
    main()
