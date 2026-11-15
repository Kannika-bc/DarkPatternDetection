"""CCPA 4 Forced Action: 'download the app to continue', 'sign in to continue reading'."""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx
from backend.rules.text_rules import scan_segments

PATTERNS = [
    rx(r"\b(download|install|get|use) (the |our )?(\w+ )?app to (continue|view|see|read|browse|access|order|unlock)\b"),
    rx(r"\b(sign in|log ?in|register|sign up|create (a |an )?(free )?account)\b.{0,40}\bto (continue|keep|read|view|see|access|unlock)\b"),
    rx(r"\bto read the rest of\b"),
    rx(r"\b(share|enter) your (contacts|phone number|location) to (continue|proceed)\b"),
]
EXCLUDE = [rx(r"\boptional\b")]


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    return scan_segments(snapshot, "FORCED_ACTION", PATTERNS, exclude=EXCLUDE, confidence=0.85,
                         status="confirmed")
