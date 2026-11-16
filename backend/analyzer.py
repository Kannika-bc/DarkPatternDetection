"""The DarkLens analysis pipeline (pure Python, no web framework).

PageSnapshot -> page type -> rules -> ML -> merge + confidence -> CCPA mapping -> AnalyzeResponse
"""

from __future__ import annotations

import os
import re
import time
from functools import lru_cache
from typing import Optional

from backend.merger import merge, trust_score
from backend.models import AnalyzeResponse, PageSnapshot, PriceObservation
from backend.page_type import detect_page_type
from backend.prices import parse_price
from backend.rules import run_rules
from backend.rules.base import RuleContext
from backend.rules.drip_pricing import FEE, NORMAL, TOTAL


# Which ML model the live analyzer uses. DistilBERT scores best on the benchmark test set, but on
# real page text (prices, fee rows, menu labels) it is over-confident: our test-site evaluation
# showed it >97 % sure that "Item total" or "Rs 25.00" are dark patterns. MiniLM + LR is far better
# calibrated on such text (see scripts/evaluate_test_site.py), so it is the default here.
# Override with the environment variable DARKLENS_MODEL=distilbert|minilm_lr|tfidf_lr|auto.
LIVE_MODEL = os.environ.get("DARKLENS_MODEL", "minilm_lr")


@lru_cache(maxsize=1)
def get_classifier():  # -> Optional[DarkPatternClassifier]
    """Load the ML classifier once. Returns None if no trained model is available."""
    try:
        from ml.predictor import DarkPatternClassifier, available_models

        model = LIVE_MODEL if LIVE_MODEL in available_models() else "auto"
        clf = DarkPatternClassifier(model=model)
        return clf if clf.available else None
    except Exception as exc:  # missing model files or ML deps: run with rules only
        print(f"[analyzer] ML classifier unavailable, using rules only: {exc}")
        return None


def _normalise_prices(snapshot: PageSnapshot) -> None:
    """Re-parse prices with the Python parser (the JS parser is only a rough first pass)."""
    for p in snapshot.prices:
        parsed = parse_price(p.raw_text)
        if parsed:
            p.value, p.currency = parsed.value, parsed.currency


def product_label(title: str) -> str:
    """'Boltwave X2 Earbuds | Kartiq' -> 'Boltwave X2 Earbuds'."""
    return re.split(r"\s[|–—-]\s", title)[0].strip()[:80] or title[:80]


def price_observation(snapshot: PageSnapshot, page_type: str) -> Optional[PriceObservation]:
    """Main price on a product page: first visible, non-struck price that is not a fee or total."""
    if page_type != "product":
        return None
    for p in snapshot.prices:
        ctx = p.context or ""
        if p.value and not p.struck_through and not FEE.search(ctx) and not TOTAL.search(ctx) and not NORMAL.search(ctx):
            return PriceObservation(label=product_label(snapshot.title), value=p.value, currency=p.currency,
                                    url=snapshot.url)
    return None


def analyze(snapshot: PageSnapshot, use_ml: bool = True) -> AnalyzeResponse:
    t0 = time.perf_counter()
    _normalise_prices(snapshot)
    page_type = detect_page_type(snapshot)
    detections = run_rules(snapshot, RuleContext(page_type=page_type))
    findings = merge(detections, snapshot, get_classifier() if use_ml else None)
    return AnalyzeResponse(
        url=snapshot.url, page_type=page_type, trust_score=trust_score(findings), findings=findings,
        price_observation=price_observation(snapshot, page_type),
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
    )
