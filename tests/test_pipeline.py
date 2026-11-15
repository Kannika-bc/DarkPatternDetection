"""Merger, page type, analyzer, API and ML predictor tests (no browser needed)."""

import pytest
from fastapi.testclient import TestClient

from backend.analyzer import analyze, product_label
from backend.main import app
from backend.merger import merge, trust_score
from backend.page_type import detect_page_type
from backend.rules.base import Detection
from tests.helpers import button, price, snap


def test_merger_dedupes_and_maps_ccpa():
    s = snap(segments=["Hurry! ends in 10:00"])
    dets = [Detection("FALSE_URGENCY", "Hurry! ends in 10:00", "s0", 0.75),
            Detection("FALSE_URGENCY", "10:00", "t1", 0.95, "confirmed")]
    findings = merge(dets, s)
    assert len(findings) == 1
    f = findings[0]
    assert f.ccpa_ref == 1 and f.status == "confirmed" and "CCPA" in f.explanation


def test_trust_score_bounds():
    assert trust_score([]) == 100
    many = merge([Detection("DRIP_PRICING", f"fee {i}", f"e{i}", 1.0, "confirmed") for i in range(20)], snap())
    assert trust_score(many) == 0


def test_page_type():
    assert detect_page_type(snap(title="Your cart", segments=["Subtotal (2 items)"])) == "cart"
    assert detect_page_type(snap(title="Checkout", segments=["Order summary", "Continue to payment"])) == "checkout"
    s = snap(title="Wireless Earbuds", segments=["In stock"], buttons=[button("b", "Add to cart")])
    assert detect_page_type(s) == "product"


def test_analyze_returns_price_observation_on_product_page():
    s = snap(title="Boltwave X2 Earbuds | Kartiq", segments=["Add to cart", "Buy now"],
             prices=[price("p1", "₹14,999", "₹14,999 ₹1,499", struck=True), price("p2", "₹1,499", "₹14,999 ₹1,499")])
    res = analyze(s, use_ml=False)
    assert res.page_type == "product"
    assert res.price_observation and res.price_observation.value == 1499.0
    assert product_label("Boltwave X2 Earbuds | Kartiq") == "Boltwave X2 Earbuds"


def test_api_health_and_analyze():
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    body = snap(segments=["Only 2 left in stock!"]).model_dump()
    res = client.post("/analyze", json=body)
    assert res.status_code == 200
    assert any(f["type"] == "FAKE_SCARCITY" for f in res.json()["findings"])
    assert client.post("/analyze", json={**body, "cookies": "x"}).status_code == 422  # unknown field


def test_predictor_if_trained():
    from ml.predictor import DarkPatternClassifier, available_models

    if not available_models():
        pytest.skip("no trained model")
    clf = DarkPatternClassifier(model="tfidf_lr")
    out = clf.predict(["Only 2 left in stock! Hurry!", "Free shipping on orders over $50"])
    assert len(out) == 2 and out[0][0] == "dark" and 0.5 <= out[0][1] <= 1.0
    assert clf.predict([]) == []
    assert len(clf.predict_category(["Only 2 left in stock"])) == 1
