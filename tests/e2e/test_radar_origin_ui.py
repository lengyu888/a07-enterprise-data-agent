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

from playwright.sync_api import sync_playwright  # noqa: E402


BASE_URL = "http://localhost:8080"
ARTIFACTS = ROOT / "artifacts"


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE_URL, wait_until="networkidle")
        page.evaluate(
            """
            document.body.insertAdjacentHTML(
              'beforeend',
              '<div id="radar-origin-fixture" class="radar-loader" style="--machine-yellow:#ffe875;--machine-orange:#ff5a36;--ink:#17213d;--blue:#2457ff"><i></i><b></b></div>'
            )
            """
        )

        radar = page.locator("#radar-origin-fixture")
        scan = radar.locator("i")
        scan.evaluate(
            "element => { element.style.animation = 'none'; element.style.transform = 'rotate(0deg)' }"
        )
        geometry = page.evaluate(
            """
            () => {
              const radar = document.querySelector('#radar-origin-fixture').getBoundingClientRect()
              const scan = document.querySelector('#radar-origin-fixture i')
              const line = scan.getBoundingClientRect()
              const style = getComputedStyle(scan)
              return {
                radarCenterX: radar.left + radar.width / 2,
                radarCenterY: radar.top + radar.height / 2,
                lineStartX: line.left,
                lineCenterY: line.top + line.height / 2,
                transformOrigin: style.transformOrigin,
              }
            }
            """
        )
        assert abs(geometry["lineStartX"] - geometry["radarCenterX"]) <= 0.5
        assert abs(geometry["lineCenterY"] - geometry["radarCenterY"]) <= 0.5
        assert geometry["transformOrigin"].split()[0] == "0px"

        scan.evaluate("element => { element.style.transform = 'rotate(135deg)' }")
        radar.screenshot(
            path=str(ARTIFACTS / "radar-origin-fixed.png"), animations="disabled"
        )
        browser.close()


if __name__ == "__main__":
    main()
