"""Collector B: build a PageSnapshot with Playwright (a real Chromium browser).

Why a real browser? Modern sites render prices, timers and popups with JavaScript, so a plain
HTTP request + BeautifulSoup would miss them.

How: we inject the SAME collection script the Chrome extension uses
(``extension/content/collector.js``), so both collectors produce identical PageSnapshots.
Python adds what only a controlling browser can do: wait for the page to settle, reload the page to
check whether countdown timers restart, and validate the result with Pydantic.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

from backend.models import PageSnapshot
from backend.prices import parse_price

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR_JS = (ROOT / "extension" / "content" / "collector.js").read_text(encoding="utf-8")

DEFAULT_SETTLE_MS = 3000  # popups and injected content often appear a few seconds after load


def _ensure_script(page: Page) -> None:
    """Inject collector.js into the page if it is not there yet."""
    if not page.evaluate("() => !!window.DarkLensCollector"):
        page.add_script_tag(content=COLLECTOR_JS)


def _clean_prices(raw: dict[str, Any]) -> None:
    """Re-parse each price with the tested Python parser (authoritative value + currency)."""
    for price in raw.get("prices", []):
        parsed = parse_price(price.get("raw_text", ""))
        if parsed:
            price["value"] = parsed.value
            price["currency"] = parsed.currency


def collect_snapshot(page: Page) -> PageSnapshot:
    """Collect a PageSnapshot from an already-open Playwright page."""
    _ensure_script(page)
    raw = page.evaluate("() => window.DarkLensCollector.collect('playwright')")
    _clean_prices(raw)
    return PageSnapshot.model_validate(raw)


def settle(page: Page, settle_ms: int = DEFAULT_SETTLE_MS) -> None:
    """Wait until the network is quiet, then a little longer for delayed popups/content."""
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:  # some sites never go fully idle (analytics, websockets)
        pass
    page.wait_for_timeout(settle_ms)


def check_timer_resets(page: Page, snapshot: PageSnapshot) -> None:
    """Reload the page and compare countdowns. A timer that goes back UP after a reload is fake.

    Modifies ``snapshot.timers[*].reset_on_reload`` in place.
    """
    timed = [t for t in snapshot.timers if t.seconds_left is not None]
    if not timed:
        return
    start = time.monotonic()
    page.wait_for_timeout(2000)  # let the real clock run a little
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    after = collect_snapshot(page)
    elapsed = time.monotonic() - start
    after_values = [t.seconds_left for t in after.timers if t.seconds_left is not None]
    for i, timer in enumerate(timed):
        if i < len(after_values):
            # A real deadline keeps counting down: by now it should show about (before - elapsed).
            # If the reloaded page shows clearly MORE time than that, the countdown restarted.
            expected_now = (timer.seconds_left or 0) - elapsed
            timer.reset_on_reload = after_values[i] > expected_now + 1.5


def collect_url(
    url: str,
    *,
    headless: bool = True,
    settle_ms: int = DEFAULT_SETTLE_MS,
    check_reload: bool = True,
) -> PageSnapshot:
    """Open ``url`` in Chromium, wait for it to settle and return its PageSnapshot."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("Only http(s) URLs are allowed")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            settle(page, settle_ms)
            snapshot = collect_snapshot(page)
            if check_reload:
                check_timer_resets(page, snapshot)
            return snapshot
        finally:
            browser.close()
