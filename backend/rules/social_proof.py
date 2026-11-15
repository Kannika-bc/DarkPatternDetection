"""Fake social proof: '27 people are viewing this', 'ordered 500+ times in the last hour'.

A static aggregate rating ("4.3 from 2,140 verified ratings") is normal and not flagged.
"""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx
from backend.rules.text_rules import scan_segments

PATTERNS = [
    rx(r"\b\d[\d,]*\+? (people|persons|users|shoppers|customers|others|travell?ers)\b.{0,30}"
       r"\b(viewing|watching|looking|bought|booked|ordered|purchased|added)\b"),
    rx(r"\b(ordered|booked|bought|sold|purchased|viewed)\s+\d[\d,]*\+?\s+times?\b"),
    rx(r"\b(booked|bought|ordered|sold|viewed)\b.{0,40}\bin the (last|past) (\d+ )?(hour|hours|minutes?)\b"),
    rx(r"\b(someone|a customer) (in|from) [A-Z]\w+ (just )?(bought|booked|ordered)\b"),
]


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    return scan_segments(snapshot, "FAKE_SOCIAL_PROOF", PATTERNS, confidence=0.8)
