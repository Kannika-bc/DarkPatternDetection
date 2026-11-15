"""Guess what kind of page a snapshot shows: product, cart, checkout, signup, subscription, article, other.

Simple keyword scoring over the URL, the title, the button texts and the visible text. Transparent
and fast; rules use it to adjust confidence (e.g. fees on a checkout page are expected to be listed).
"""

from __future__ import annotations

import re

from backend.models import PageSnapshot

SIGNALS: dict[str, list[tuple[str, float]]] = {
    "checkout": [(r"\bcheckout\b", 3), (r"\b(continue|proceed) to (payment|pay)\b", 3), (r"\border summary\b", 2),
                 (r"\b(delivery|shipping|billing) address\b", 2), (r"\breview your booking\b", 3),
                 (r"\bfare summary\b", 2), (r"\bpayment method\b", 1)],
    "cart": [(r"\b(your |shopping )?(cart|basket|bag)\b", 2), (r"\bsubtotal\b", 2), (r"\bproceed to checkout\b", 3),
             (r"\bbill details\b", 2), (r"\bto pay\b", 1)],
    "product": [(r"\badd to (cart|bag|basket)\b", 3), (r"\bbuy now\b", 3), (r"\bbook\b", 1), (r"\bin stock\b", 1),
                (r"\bmrp\b", 1), (r"\b(ratings?|reviews?)\b", 1), (r"\bmenu\b", 1), (r"\badd\b", 1),
                (r"\b(book|select|book now)\b", 1.5), (r"\b(flights?|hotels?|non-stop|per night)\b", 1)],
    "signup": [(r"\b(sign ?up|create (your |an )?account|register)\b", 3), (r"\bpassword\b", 1)],
    "subscription": [(r"\b(plans?|membership|subscription)\b", 2), (r"/ ?(month|mo|year)\b", 2),
                     (r"\bfree trial\b", 2), (r"\b(cancel|renew)\w*\b", 1), (r"\bbilling date\b", 2)],
    "article": [(r"\b\d+ min read\b", 3), (r"\bby (staff )?reporter\b", 2), (r"\b(blog|news|story|article)\b", 1)],
}


def detect_page_type(snapshot: PageSnapshot) -> str:
    """Return the most likely page type (or "other")."""
    head = f"{snapshot.url} {snapshot.title}".lower()
    body = " ".join(s.text for s in snapshot.segments[:400]).lower()
    buttons = " ".join(b.text for b in snapshot.buttons).lower()
    scores: dict[str, float] = {}
    for page_type, signals in SIGNALS.items():
        score = 0.0
        for pattern, weight in signals:
            if re.search(pattern, head):
                score += weight * 2  # URL/title are strong signals
            if re.search(pattern, buttons):
                score += weight
            if re.search(pattern, body):
                score += weight * 0.5
        scores[page_type] = score
    # Long text with few prices looks like an article.
    if len(body) > 1500 and len(snapshot.prices) <= 2:
        scores["article"] += 3
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] >= 3 else "other"
