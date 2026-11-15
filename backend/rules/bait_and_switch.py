"""CCPA 7 Bait and Switch: the same product now costs more than when it was first shown.

Needs ``previous_prices`` (first price seen for each product on this site). We match a product by the
words its label shares with the text around a current price.
"""

from __future__ import annotations

import re

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx

PRICE_CHANGED = rx(r"\bprice (has )?(updated|changed|increased|revised)\b")
_WORD = re.compile(r"[a-z]{3,}")


def tokens(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def same_product(label: str, context: str, threshold: float = 0.6) -> bool:
    """True if most words of the shorter text appear in the other one."""
    a, b = tokens(label), tokens(context)
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= threshold


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    found: list[Detection] = []
    for prev in snapshot.previous_prices:
        for p in snapshot.prices:
            if p.struck_through or not p.value or not p.context:
                continue
            if p.currency and prev.currency and p.currency != prev.currency:
                continue
            if same_product(prev.label, p.context) and p.value > prev.value * 1.02:
                found.append(Detection(
                    "BAIT_AND_SWITCH", p.context, p.id, 0.9, "confirmed",
                    note=f"'{prev.label}' was shown for {prev.value:,.0f}, now {p.value:,.0f}."))
                break
    if not found:  # single-page hint: "Price updated" next to a price
        for p in snapshot.prices:
            if p.context and PRICE_CHANGED.search(p.context):
                found.append(Detection("BAIT_AND_SWITCH", p.context, p.id, 0.55,
                                       note="The page says the price changed after you chose the product."))
                break
    return found
