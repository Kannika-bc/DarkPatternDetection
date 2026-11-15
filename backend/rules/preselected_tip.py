"""Pre-selected tip or donation (related to CCPA 2 Basket Sneaking). Fixable.

* Radio group about a tip/donation where an option other than "no tip"/"0" is selected by default.
* A tip/donation checkbox that is already ticked.
"""

from __future__ import annotations

from backend.models import Checkbox, PageSnapshot
from backend.rules.base import Detection, RuleContext, rx

TIP = rx(r"\b(tip|tips|tipped|donat\w*|contribut\w*|charity|fund|round[- ]?up|plantation drive)\b")
NO_OPTION = rx(r"^\s*(no\b|none|no tip|not now|skip|0\b|₹\s?0\b|rs\.?\s?0\b)")


def is_tip(cb: Checkbox) -> bool:
    return bool(TIP.search(cb.label) or TIP.search(cb.group_label or ""))


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    found: list[Detection] = []
    # Radio groups
    groups: dict[str, list[Checkbox]] = {}
    for cb in snapshot.checkboxes:
        if cb.type == "radio" and cb.group:
            groups.setdefault(cb.group, []).append(cb)
    for options in groups.values():
        if not any(is_tip(o) for o in options):
            continue
        selected = [o for o in options if o.checked]
        if selected and not NO_OPTION.search(selected[0].label):
            question = options[0].group_label or "Tip / donation"
            found.append(Detection(
                "PRESELECTED_TIP", f"{question}: '{selected[0].label}' selected by default",
                selected[0].id, 0.9, "confirmed"))
    # Single checkboxes
    for cb in snapshot.checkboxes:
        if cb.type == "checkbox" and cb.checked and is_tip(cb):
            found.append(Detection("PRESELECTED_TIP", cb.label, cb.id, 0.9, "confirmed"))
    return found
