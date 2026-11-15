"""CCPA 5 Subscription Trap: cancelling only by phone / offline / in a narrow window."""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx
from backend.rules.text_rules import scan_segments

PATTERNS = [
    rx(r"\b(cannot|can'?t|can not) be (cancell?ed|terminated) online\b"),
    rx(r"\bto (cancel|end|terminate)\b.{0,60}\b(call|phone|visit|write to|post a letter)\b"),
    rx(r"\b(cancell?ation|cancel)s? (is |are )?only (possible|available|accepted) (by|via|through)\b"),
]
# Honest wording: "You can cancel online at any time".
EXCLUDE = [rx(r"\bcan cancel online\b")]


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    return scan_segments(snapshot, "SUBSCRIPTION_TRAP", PATTERNS, exclude=EXCLUDE, confidence=0.8)
