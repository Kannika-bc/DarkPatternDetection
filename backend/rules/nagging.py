"""CCPA 10 Nagging: a popup request (rate us, notifications, newsletter, app) that offers only
'later' and no permanent 'no'. Confirmed when the popup was seen more than once."""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx

REQUEST = rx(r"\b(rate us|rate the app|\d stars|allow\b.{0,50}\bnotifications?|(enable|turn on) notifications|"
             r"subscribe to|newsletter|download (the|our) app|install (the|our) app|get the app)\b")
SOFT_DISMISS = rx(r"\b(later|not now|remind me|maybe)\b")
PERMANENT_NO = rx(r"\b(never|don'?t (ask|show)|no,? thanks|no thank you|unsubscribe)\b")


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    found: list[Detection] = []
    for popup in snapshot.popups:
        if not REQUEST.search(popup.text) or "cookie" in popup.text.lower():
            continue
        buttons = [b for b in snapshot.buttons if b.popup_id == popup.id]
        soft = any(SOFT_DISMISS.search(b.text) for b in buttons)
        permanent = any(PERMANENT_NO.search(b.text) for b in buttons)
        if permanent:
            continue
        if popup.times_shown >= 2:
            found.append(Detection("NAGGING", popup.text[:200], popup.id, 0.9, "confirmed",
                                   note=f"This popup has appeared {popup.times_shown} times."))
        elif soft:
            found.append(Detection("NAGGING", popup.text[:200], popup.id, 0.65,
                                   note="The popup offers only 'later', never a permanent 'no'."))
    return found
