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
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="智能问析 04").click()
        assert "RAG ROUTES" in page.locator(".agent-badge").inner_text()
        assert page.locator(".example-switcher button").count() == 3
        page.get_by_role("button", name="启动智能问析 →").click()
        page.get_by_text("HYBRID RETRIEVAL LEDGER", exact=True).wait_for(timeout=240_000)
        assert page.locator(".rag-channel").count() == 3
        assert page.locator(".trace-rail article").count() >= 7
        sql_badge = page.locator(".sql-card>header>span")
        assert "SQLGLOT PASSED" in sql_badge.inner_text()
        assert "REPAIR" in sql_badge.inner_text()
        assert page.locator(".yield-chart .bar-column").count() == 3
        assert page.locator(".source-proof>span").count() >= 4
        assert page.locator(".agent-error").count() == 0
        page.wait_for_timeout(700)
        page.screenshot(path=ARTIFACT_DIR / "stage3-rag-agent-desktop.png", full_page=True)

        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile.goto(BASE_URL)
        mobile.wait_for_load_state("networkidle")
        mobile.locator(".view-nav button").nth(3).click()
        mobile.wait_for_timeout(550)
        assert mobile.locator(".example-switcher button").count() == 3
        mobile.screenshot(path=ARTIFACT_DIR / "stage3-rag-agent-mobile.png", full_page=True)
        browser.close()
    assert not console_errors, f"Browser console errors: {console_errors}"
    print("Stage 3 browser test passed")


if __name__ == "__main__":
    main()
