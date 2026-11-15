"""CCPA 11 Trick Question: consent wording with double negatives.

Example: "Uncheck this box if you do not wish to not receive offers" (3 negations).
Rule: a checkbox label with 2+ negation words.
"""

from __future__ import annotations

import re

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext

NEGATION = re.compile(r"\b(not|don'?t|never|no|uncheck|untick|opt[- ]?out|unsubscribe|decline|without)\b",
                      re.IGNORECASE)


def negation_count(text: str) -> int:
    return len(NEGATION.findall(text or ""))


def is_trick(label: str) -> bool:
    return negation_count(label) >= 2


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    found: list[Detection] = []
    for cb in snapshot.checkboxes:
        if cb.type == "checkbox" and is_trick(cb.label):
            state = "ticked" if cb.checked else "unticked"
            found.append(Detection(
                "TRICK_QUESTION", cb.label, cb.id, 0.8,
                note=f"{negation_count(cb.label)} negative words in one sentence; the box is currently {state}."))
    return found
