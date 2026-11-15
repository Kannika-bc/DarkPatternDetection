"""CCPA 12 SaaS Billing: a free trial that silently converts to a paid plan.

Flagged when auto-charge wording appears with a trial (or "no reminder") and the page does NOT
promise to remind the user first.
"""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx

AUTO_CHARGE = rx(r"\b(automatically (be )?(charged|billed|debited|renewed)|auto[- ]?(debit|charge|renew)s?|"
                 r"(will|shall) be (charged|billed|debited))\b")
TRIAL = rx(r"\b(trial|free for \d+ days|\d+[- ]day free)\b")
NO_REMINDER = rx(r"\bno (reminder|notification|notice|email)s? (will be|is) sent\b|\bwithout (any )?(reminder|notice)\b")
HONEST = rx(r"\b(we'?ll|we will) (email|remind|notify|tell) you\b|\bonly (be )?charged if you (choose|decide|opt)\b")


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    found: list[Detection] = []
    for seg in snapshot.segments:
        t = seg.text
        if HONEST.search(t):
            continue
        if AUTO_CHARGE.search(t) and (TRIAL.search(t) or NO_REMINDER.search(t)):
            conf = 0.9 if NO_REMINDER.search(t) else 0.75
            note = "Auto-charge terms hidden in small print." if seg.fine_print else ""
            found.append(Detection("SAAS_BILLING", t, seg.id, conf, note=note))
    return found
