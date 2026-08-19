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


@pytest.mark.parametrize("viewport_name", sorted(VIEWPORTS))
def test_orbital_iq_mission_control_links_to_real_pages(playwright_page, viewport_name):
    """Mission Control is the overview; deeper panels now live on their own
    real pages, linked from here. Only the SAR/AIS map layer stays CONCEPT."""
    viewport = VIEWPORTS[viewport_name]
    page = playwright_page.new_page(viewport=viewport)
    dialogs = []
    page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    page.goto(
        BASE_URL.rstrip("/") + "/dashboard/orbital-iq",
        wait_until="networkidle",
        timeout=45_000,
    )
    page.wait_for_timeout(2_000)

    # .panel-head h2 renders text-transform:uppercase, so compare case-insensitively.
    body_text = page.locator("body").inner_text().lower()
    assert "mission control" in body_text
    # Exactly two CONCEPT badges: the page-level disclosure and the map's own
    # SAR/AIS banner. Every other panel shows real data or links to a real page.
    assert body_text.count("concept") == 2, "only the SAR/AIS map layer should stay badged CONCEPT"
    for claim in ("infrastructure health", "events", "commercial ops"):
        assert claim in body_text, f"missing real panel or link: {claim}"

    # The Events and Commercial Ops teaser cards must navigate for real.
    page.click("a.nav-item[href='/dashboard/events']")
    page.wait_for_load_state("networkidle")
    assert page.url.endswith("/dashboard/events")
    page.go_back()
    page.wait_for_timeout(500)
    page.click("a.nav-item[href='/dashboard/commercial']")
    page.wait_for_load_state("networkidle")
    assert page.url.endswith("/dashboard/commercial")
    page.go_back()
    page.wait_for_timeout(500)

    # The one remaining fabricated layer must still refuse to switch on.
    page.click("input[data-layer='sar']")
    page.wait_for_timeout(300)
    assert page.is_checked("input[data-layer='sar']") is False
    assert dialogs, "enabling a non-existent feed must explain that it isn't real"

    # A disabled nav item must explain itself instead of doing nothing.
    dialogs.clear()
    page.click("div.nav-item.disabled[data-noreal='Reports']")
    page.wait_for_timeout(300)
    assert dialogs, "clicking an unwired nav item must explain that it isn't real"

    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    assert scroll_width <= viewport["width"] + 1, (
        f"page scrollWidth {scroll_width} exceeds viewport width "
        f"{viewport['width']} at {viewport_name}"
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(ARTIFACT_DIR / f"orbital-iq-{viewport_name}.png"), full_page=True
    )
    page.close()


@pytest.mark.parametrize("viewport_name", sorted(VIEWPORTS))
def test_orbital_iq_events_run_log_is_real_and_clickable(playwright_page, viewport_name):
    """Events page: real run log, clicking a row swaps in that run's real detail/economics."""
    viewport = VIEWPORTS[viewport_name]
    page = playwright_page.new_page(viewport=viewport)
    page.goto(
        BASE_URL.rstrip("/") + "/dashboard/events",
        wait_until="networkidle",
        timeout=45_000,
    )
    page.wait_for_timeout(1_000)

    rows = page.locator("tr.run-row")
    assert rows.count() > 0, "real workload matrix must populate the run log"

    # Pick a row that isn't already selected (default selection is ship-detect
    # if present) so the click provably changes the detail panel's content.
    target = None
    for i in range(rows.count()):
        row = rows.nth(i)
        if "sel" not in (row.get_attribute("class") or ""):
            target = row
            break
    assert target is not None, "expected at least one non-default row to click"
    slug = target.get_attribute("data-slug")
    target.click()
    page.wait_for_timeout(300)
    assert "sel" in (target.get_attribute("class") or ""), "clicked row must become selected"

    body_text = page.locator("#detail-body").inner_text()
    assert body_text, "run detail panel must populate after selecting a real run"
    econ_text = page.locator("#econ-body").inner_text()
    assert "₹" in econ_text, "run economics panel must show real cost figures"

    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    assert scroll_width <= viewport["width"] + 1, (
        f"page scrollWidth {scroll_width} exceeds viewport width "
        f"{viewport['width']} at {viewport_name}"
    )
    page.close()


@pytest.mark.parametrize("viewport_name", sorted(VIEWPORTS))
def test_orbital_iq_commercial_ops_is_real_no_fabricated_revenue(playwright_page, viewport_name):
    """Commercial Ops must show real workload economics and must never claim
    customer or revenue figures that don't exist."""
    viewport = VIEWPORTS[viewport_name]
    page = playwright_page.new_page(viewport=viewport)
    page.goto(
        BASE_URL.rstrip("/") + "/dashboard/commercial",
        wait_until="networkidle",
        timeout=45_000,
    )
    page.wait_for_timeout(1_000)

    body_text = page.locator("body").inner_text().lower()
    assert "workload coverage" in body_text
    assert "aggregate economics" in body_text
    assert "no customers, contracts, or revenue exist" in body_text
    for fabricated in (
        "contracted arr",
        "recognized mrr",
        "sla compliance",
        "indian ocean maritime watch",  # the mockup's fabricated customer name
    ):
        assert fabricated not in body_text, f"fabricated commercial figure present: {fabricated}"

    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    assert scroll_width <= viewport["width"] + 1, (
        f"page scrollWidth {scroll_width} exceeds viewport width "
        f"{viewport['width']} at {viewport_name}"
    )
    page.close()


@pytest.mark.parametrize("viewport_name", sorted(VIEWPORTS))
def test_orbital_map_is_real_and_interactive(playwright_page, viewport_name):
    """The dedicated map page must load real satellites, let you select one,
    refuse the fabricated SAR/AIS layers, and stay usable on mobile."""
    viewport = VIEWPORTS[viewport_name]
    page = playwright_page.new_page(viewport=viewport)
    dialogs = []
    page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    page.goto(
        BASE_URL.rstrip("/") + "/dashboard/map",
        wait_until="networkidle",
        timeout=45_000,
    )
    page.wait_for_timeout(3_000)  # let at least one real /api/overhead poll land

    rows = page.locator(".sat-row")
    assert rows.count() > 0, "real satellite catalog must populate the sidebar list"

    if viewport_name == "mobile":
        page.click("#side-toggle")
        page.wait_for_timeout(300)
    rows.first.click()
    page.wait_for_timeout(800)
    assert page.locator("#sat-card").is_visible(), "selecting a satellite must show its real detail card"

    page.click("input[data-layer='ais']")
    page.wait_for_timeout(300)
    assert page.is_checked("input[data-layer='ais']") is False
    assert dialogs, "enabling a non-existent AIS feed must explain that it isn't real"

    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    assert scroll_width <= viewport["width"] + 1, (
        f"page scrollWidth {scroll_width} exceeds viewport width "
        f"{viewport['width']} at {viewport_name}"
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACT_DIR / f"map-{viewport_name}.png"), full_page=True)
    page.close()
