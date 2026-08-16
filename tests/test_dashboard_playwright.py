import os
from pathlib import Path

import pytest

BASE_URL = os.environ.get("ARIES_DASHBOARD_BASE_URL")
pytestmark = pytest.mark.skipif(
    BASE_URL is None,
    reason="Live dashboard (Compose stack) is not configured",
)

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "mobile": {"width": 390, "height": 844},
}
ARTIFACT_DIR = Path(
    os.environ.get("ARIES_SCREENSHOT_DIR", "dashboard-screenshots")
)


@pytest.fixture(scope="module")
def playwright_page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            yield browser
        finally:
            browser.close()


@pytest.mark.parametrize("viewport_name", sorted(VIEWPORTS))
def test_dashboard_renders_benchmark_comparison_honestly(playwright_page, viewport_name):
    viewport = VIEWPORTS[viewport_name]
    page = playwright_page.new_page(viewport=viewport)
    page.goto(BASE_URL, wait_until="networkidle", timeout=30_000)

    assert page.locator("text=Benchmark Comparison").count() > 0

    # No page-level horizontal overflow at either viewport.
    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    assert scroll_width <= viewport["width"] + 1, (
        f"page scrollWidth {scroll_width} exceeds viewport width "
        f"{viewport['width']} at {viewport_name}"
    )

    body_text = page.locator("body").inner_text()
    # If a benchmark pair exists, both honesty labels must be visible;
    # otherwise the section must render its explicit no-data state, not a
    # blank/broken one.
    if "No placement recommendation" not in body_text and "Benchmark comparison is temporarily unavailable" not in body_text and "No benchmark pair has been run yet" not in body_text:
        assert "SIMULATED" in body_text
        assert "ESTIMATED" in body_text

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(ARTIFACT_DIR / f"dashboard-{viewport_name}.png"), full_page=True
    )
    page.close()
