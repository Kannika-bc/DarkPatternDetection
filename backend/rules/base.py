"""Shared types and helpers for the rule engine.

Every rule module exposes ``detect(snapshot, ctx) -> list[Detection]``. A Detection is a raw rule
hit; the merger later turns it into a ``Finding`` (adds CCPA ref, severity, explanation, id...).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from backend.models import Button, PageSnapshot


@dataclass
class Detection:
    type: str  # pattern type, e.g. "FALSE_URGENCY"
    text: str  # evidence shown to the user
    element_id: Optional[str]
    confidence: float  # 0..1
    status: str = "unverified"  # confirmed | unverified
    source: str = "rule"
    note: str = ""  # extra explanation specific to this hit (e.g. "timer restarted on reload")


@dataclass
class RuleContext:
    page_type: str = "other"
    extras: dict = field(default_factory=dict)


def rx(pattern: str) -> re.Pattern[str]:
    """Case-insensitive regex helper."""
    return re.compile(pattern, re.IGNORECASE)


def find_first(patterns: list[re.Pattern[str]], text: str) -> Optional[re.Match[str]]:
    for p in patterns:
        m = p.search(text)
        if m:
            return m
    return None


# ---------------------------------------------------------------- colour / contrast (WCAG 2.1)

_RGB = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\s*\)")


def parse_rgb(css: str) -> tuple[float, float, float]:
    """'rgb(255, 0, 0)' -> (255, 0, 0). Unknown formats -> white."""
    m = _RGB.search(css or "")
    if not m:
        return (255.0, 255.0, 255.0)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3)))


def _luminance(rgb: tuple[float, float, float]) -> float:
    def channel(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg_css: str, bg_css: str) -> float:
    """WCAG contrast ratio between text and background (1 = invisible, 21 = black on white)."""
    l1, l2 = _luminance(parse_rgb(fg_css)), _luminance(parse_rgb(bg_css))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def visual_weight(b: Button) -> float:
    """How much a button 'shouts': area x font size, halved if its text is hard to read."""
    weight = max(b.width * b.height, 1.0) * max(b.font_size, 1.0)
    if contrast_ratio(b.text_color, b.bg_color) < 3.0:
        weight *= 0.5
    return weight


def buttons_by_group(snapshot: PageSnapshot) -> dict[str, list[Button]]:
    """Group buttons that are shown together as one choice (same group_id)."""
    groups: dict[str, list[Button]] = {}
    for b in snapshot.buttons:
        if b.group_id:
            groups.setdefault(b.group_id, []).append(b)
    return groups


DECLINE_RE = rx(r"^\s*(no\b|nope|nah|not now|maybe later|later|skip|cancel|reject|decline|refuse|"
                r"i don'?t|i do not|i'?ll pass|close|dismiss|continue without|manage options)")
ACCEPT_RE = rx(r"^\s*(yes|accept|allow|ok\b|okay|agree|got it|continue|start|keep|protect|get|"
               r"sign up|subscribe|add|buy|book|rate|i want)")
