"""Auto-renew switched ON by default (related to CCPA 12 SaaS Billing). Fixable: switch it off."""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx

RENEW = rx(r"\b(auto[- ]?renew(al|s)?|renews? automatically|automatic(ally)? renew(al)?|recurring (payment|billing)|autopay)\b")


def is_renew(label: str) -> bool:
    return bool(RENEW.search(label or ""))


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    return [
        Detection("AUTO_RENEW", cb.label, cb.id, 0.9, "confirmed",
                  note="Automatic renewal was already switched on.")
        for cb in snapshot.checkboxes
        if cb.type == "checkbox" and cb.checked and is_renew(cb.label)
    ]
