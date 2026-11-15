"""CCPA 3 Confirm Shaming: a decline option worded to guilt the user.

Rule: the text starts like a refusal ("No thanks", "Cancel anyway", "I don't...") AND continues with
a guilt-tripping first-person phrase ("I prefer paying full price", "I'm okay losing my money").
A plain "No thanks" is fine and is NOT flagged.
"""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx

DECLINE_START = rx(r"^\s*(no\b|nope|nah|cancel|skip|not now|i don'?t|i do not|i'?ll pass|i'?d rather|close)")
SHAME = [
    rx(r"\bi (prefer|like|love|enjoy) (paying|to pay|spending|missing)\b"),
    rx(r"\bfull price\b"),
    rx(r"\b(i'?m|i am) (ok|okay|fine|happy) (with )?(losing|paying|missing|being|not)\b"),
    rx(r"\bi don'?t (care|want to save|like (saving|deals|money))\b"),
    rx(r"\bi (hate|don'?t need) (saving|money|deals|discounts)\b"),
    rx(r"\b(losing|lose|waste|wasting) (my )?money\b"),
    rx(r"\bi'?d rather (pay|miss|lose)\b"),
    rx(r"\b(stay uninformed|miss out on)\b"),
]


def is_shaming(text: str) -> bool:
    """True if ``text`` is a decline option with guilt-tripping wording."""
    return bool(DECLINE_START.search(text)) and any(p.search(text) for p in SHAME)


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    found = [Detection("CONFIRM_SHAMING", b.text, b.id, 0.85) for b in snapshot.buttons if is_shaming(b.text)]
    seen = {d.text for d in found}
    for seg in snapshot.segments:  # short link-like texts that are not real buttons
        if len(seg.text) <= 100 and seg.text not in seen and is_shaming(seg.text):
            found.append(Detection("CONFIRM_SHAMING", seg.text, seg.id, 0.8))
    return found
