"""CCPA 9 Disguised Advertisement: the only 'Ad' / 'Sponsored' label is tiny fine print.

A clearly labelled ad ("ADVERTISEMENT" in normal-size text) is fine and is not flagged.
"""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx

AD_LABEL = rx(r"(^|\W)(ad|ads|sponsored|promoted|paid (post|content|partnership)|partner content|advertorial)(\W|$)")


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    found: list[Detection] = []
    for seg in snapshot.segments:
        fine = seg.fine_print or ""
        # The label is in the fine print and is short (a tag, not a paragraph of small print).
        if fine and len(fine) <= 30 and AD_LABEL.search(fine):
            found.append(Detection("DISGUISED_AD", seg.text, seg.id, 0.75,
                                   note=f"The only ad label is the tiny text '{fine}'."))
    return found
