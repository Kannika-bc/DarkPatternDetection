"""Agent guardrails, RAG lookup and one full (LLM-free) audit of the shop journey."""

import functools
import http.server
import threading
from pathlib import Path

import pytest

from agent.tools import FORBIDDEN_CLICK, BrowserTools

SITE = Path(__file__).resolve().parents[1] / "test-site"


@pytest.mark.parametrize("text", ["Continue to payment", "Proceed to pay Rs 351", "Place order", "Sign in",
                                  "Log in", "Confirm booking", "Submit", "remove"])
def test_forbidden_clicks(text):
    assert FORBIDDEN_CLICK.search(text)


@pytest.mark.parametrize("text", ["Add to cart", "Proceed to checkout", "Book", "Start free trial", "Continue"])
def test_allowed_clicks(text):
    assert not FORBIDDEN_CLICK.search(text)


def test_only_http_urls():
    tools = BrowserTools()
    assert tools.open_page("file:///C:/Windows/win.ini").startswith("blocked")
    assert tools.open_page("javascript:alert(1)").startswith("blocked")


def test_ccpa_lookup_finds_drip_pricing():
    from rag.ccpa_rag import ccpa_lookup

    hits = ccpa_lookup("platform fee and packaging charges added on the last page")
    assert hits and hits[0]["pattern"] == 8


@pytest.fixture(scope="module")
def base_url():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_shop_audit_finds_cross_page_patterns(base_url):
    from agent.auditor import run_audit

    report = run_audit(f"{base_url}/shop/product.html", use_llm=False)
    pages = [s.page_type for s in report.steps]
    assert pages == ["product", "cart", "checkout"]  # stopped before payment
    types = {f.type: f for f in report.findings}
    assert types["BAIT_AND_SWITCH"].status == "confirmed"
    assert types["DRIP_PRICING"].status == "confirmed"
    assert types["FALSE_URGENCY"].status == "confirmed"  # timer reset on reload
    assert len(report.steps) <= 15 and report.summary


def test_signup_page_with_password_field_stops_agent(base_url):
    from agent.auditor import run_audit

    report = run_audit(f"{base_url}/ott/signup.html", use_llm=False)
    assert len(report.steps) == 1 and "password" in report.stop_reason
