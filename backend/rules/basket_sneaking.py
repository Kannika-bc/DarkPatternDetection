"""CCPA 2 Basket Sneaking: items or charges added without the user choosing them."""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx
from backend.rules.text_rules import scan_segments

PATTERNS = [
    rx(r"\bauto[- ]?added\b"),
    rx(r"\b(automatically|already) added\b"),
    rx(r"\badded (for your (protection|convenience|safety)|by default)\b"),
    rx(r"\b(we('ve| have)|has been) added\b.{0,30}\b(to your|for you)\b"),
    rx(r"\bincluded by default\b"),
]


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    return scan_segments(snapshot, "BASKET_SNEAKING", PATTERNS, confidence=0.8)
