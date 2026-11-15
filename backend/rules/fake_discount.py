"""Fake discount: an inflated 'original' (struck-through) price makes the discount look huge."""

from __future__ import annotations

import re

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext

SUSPICIOUS_DISCOUNT = 0.70  # 70 %+ off an "MRP" is rarely genuine
PERCENT_OFF = re.compile(r"\b(\d{2})\s?% off\b", re.IGNORECASE)


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    found: list[Detection] = []
    struck = [p for p in snapshot.prices if p.struck_through and p.value]
    for old in struck:
        # The selling price is a non-struck price shown in the same place (same context text).
        current = [p for p in snapshot.prices
                   if not p.struck_through and p.value and p.context == old.context and p.currency == old.currency]
        if not current:
            continue
        new = current[0]
        discount = 1 - (new.value or 0) / (old.value or 1)
        if discount >= SUSPICIOUS_DISCOUNT:
            found.append(Detection(
                "FAKE_DISCOUNT", f"{old.raw_text} -> {new.raw_text} ({discount:.0%} off)", old.id, 0.7,
                note=f"A {discount:.0%} discount from a struck-through price is unusually high; the "
                     "original price may be inflated."))
    return found
