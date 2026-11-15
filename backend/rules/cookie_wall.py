"""Cookie wall: a cookie popup with no way to refuse, or one that blocks the page until you accept."""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx

COOKIE = rx(r"\bcookies?\b")
REJECT = rx(r"\b(reject|decline|refuse|deny|necessary only|essential only|only (necessary|essential))\b")
ACCEPT_TO_CONTINUE = rx(r"\baccept\b.{0,30}\b(to (keep|continue)|reading|continue)\b")


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    found: list[Detection] = []
    for popup in snapshot.popups:
        if not COOKIE.search(popup.text):
            continue
        buttons = [b for b in snapshot.buttons if b.popup_id == popup.id]
        has_reject = any(REJECT.search(b.text) for b in buttons)
        if buttons and not has_reject:
            found.append(Detection("COOKIE_WALL", popup.text[:200], popup.id, 0.85, "confirmed",
                                   note="There is no button to reject cookies."))
        elif popup.is_blocking or ACCEPT_TO_CONTINUE.search(popup.text):
            found.append(Detection("COOKIE_WALL", popup.text[:200], popup.id, 0.8, "confirmed",
                                   note="The page content is blocked until you make a cookie choice."))
    return found
