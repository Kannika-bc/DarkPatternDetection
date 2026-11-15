"""Pre-checked opt-in: a consent / add-on checkbox ticked by default. Fixable: untick it.

Tips, auto-renew and trick questions have their own rules, so they are skipped here.
Required boxes (e.g. "I agree to the Terms") and convenience boxes ("Remember me") are not opt-ins.
"""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules import auto_renew, preselected_tip, trick_question
from backend.rules.base import Detection, RuleContext, rx

NOT_AN_OPTIN = rx(r"\b(remember me|keep me (signed|logged) in|same as (billing|shipping|delivery)|show password)\b")
PAID = rx(r"(₹|rs\.?|inr|\$|€|£)\s?\d")


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    found: list[Detection] = []
    for cb in snapshot.checkboxes:
        if cb.type != "checkbox" or not cb.checked or cb.required:
            continue
        if NOT_AN_OPTIN.search(cb.label) or auto_renew.is_renew(cb.label) or preselected_tip.is_tip(cb):
            continue
        if trick_question.is_trick(cb.label):
            continue
        note = "This paid add-on was ticked for you." if PAID.search(cb.label) else "This box was ticked for you."
        found.append(Detection("PRECHECKED_OPTIN", cb.label, cb.id, 0.9, "confirmed", note=note))
    return found
