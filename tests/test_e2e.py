"""End-to-end: serve the test site, collect pages with Playwright, analyse them.

Also checks the privacy rule: pre-filled form values must never appear in a snapshot.
"""

import functools
import http.server
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from backend.analyzer import analyze  # noqa: E402
from collector.playwright_collector import collect_url  # noqa: E402

SITE = Path(__file__).resolve().parents[1] / "test-site"


@pytest.fixture(scope="module")
def base_url():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_booking_page_end_to_end(base_url):
    snap = collect_url(f"{base_url}/travel/booking.html", settle_ms=500, check_reload=False)
    res = analyze(snap, use_ml=False)
    found = {f.type for f in res.findings}
    assert {"DRIP_PRICING", "PRECHECKED_OPTIN", "PRESELECTED_TIP", "TRICK_QUESTION",
            "INTERFACE_INTERFERENCE", "CONFIRM_SHAMING", "BASKET_SNEAKING"} <= found
    assert res.page_type == "checkout"


def test_timer_reset_is_confirmed(base_url):
    snap = collect_url(f"{base_url}/shop/product.html", settle_ms=500, check_reload=True)
    assert snap.timers and snap.timers[0].reset_on_reload is True
    urgency = [f for f in analyze(snap, use_ml=False).findings if f.type == "FALSE_URGENCY"]
    assert urgency and urgency[0].status == "confirmed"


def test_clean_page_has_no_findings(base_url):
    snap = collect_url(f"{base_url}/clean/cart.html", settle_ms=500, check_reload=False)
    assert analyze(snap, use_ml=False).findings == []


def test_privacy_no_input_values(base_url):
    for path in ("ott/signup.html", "shop/checkout.html"):
        raw = collect_url(f"{base_url}/{path}", settle_ms=300, check_reload=False).model_dump_json()
        for secret in ("not-a-real-password", "test@example.com", "9999999999", "560001"):
            assert secret not in raw, f"{secret} leaked from {path}"
