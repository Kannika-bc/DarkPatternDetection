"""Helper for rules that only look at the wording of text segments.

A text rule = a pattern type + a list of regular expressions + exclusions. Keeping the phrase lists
as data makes them easy to read, test and extend (and explain in a viva).
"""

from __future__ import annotations

import re

from backend.models import PageSnapshot
from backend.rules.base import Detection


def scan_segments(
    snapshot: PageSnapshot,
    pattern_type: str,
    patterns: list[re.Pattern[str]],
    *,
    exclude: list[re.Pattern[str]] | None = None,
    confidence: float = 0.8,
    status: str = "unverified",
    max_len: int = 300,
) -> list[Detection]:
    """Return a Detection for every segment whose text matches one of ``patterns``."""
    out: list[Detection] = []
    for seg in snapshot.segments:
        text = seg.text
        if not text or len(text) > max_len:
            continue
        if exclude and any(p.search(text) for p in exclude):
            continue
        if any(p.search(text) for p in patterns):
            out.append(Detection(pattern_type, text, seg.id, confidence, status))
    return out
