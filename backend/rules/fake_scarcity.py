"""Fake scarcity: 'only 2 left', 'selling fast', 'few seats remaining'."""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx
from backend.rules.text_rules import scan_segments

PATTERNS = [
    rx(r"\bonly \d+ (\w+ ){0,3}(left|remaining|available)\b"),
    rx(r"\b\d+ (items?|seats?|rooms?|pieces?|units?|portions?) (left|remaining)\b"),
    rx(r"\b(few|limited) (seats|items|rooms|units|stock) (left|remaining)\b"),
    rx(r"\b(selling|going) fast\b"),
    rx(r"\balmost (gone|sold out)\b"),
    rx(r"\blow (in )?stock\b"),
]


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    return scan_segments(snapshot, "FAKE_SCARCITY", PATTERNS, confidence=0.8)
