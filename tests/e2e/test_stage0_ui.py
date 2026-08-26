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
        page.screenshot(path=ARTIFACT_DIR / "stage0-desktop.png", full_page=True)

        assert page.title() == "A07 · 企业智能问析桌面工作台"
        assert "企业数据底座" in page.locator("h1").inner_text()
        assert page.get_by_text("本地工程基座已就绪").is_visible()
        assert page.get_by_text("PostgreSQL / pgvector").is_visible()
        assert page.get_by_text("DeepSeek API").is_visible()

        page.get_by_role("button", name="重新检测").click()
        page.wait_for_load_state("networkidle")
        assert page.get_by_text("本地工程基座已就绪").is_visible()

        browser.close()

    assert not console_errors, f"Browser console errors: {console_errors}"
    print("Stage 0 browser test passed")


if __name__ == "__main__":
    main()
