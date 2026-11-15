"""Rule engine: one module per pattern. ``run_rules`` calls them all.

To add a pattern: create ``backend/rules/<name>.py`` with ``detect(snapshot, ctx)``, add it to
``ALL_RULES`` and add its metadata to ``backend/ccpa.py``.
"""

from __future__ import annotations

from types import ModuleType

from backend.models import PageSnapshot
from backend.rules import (auto_renew, bait_and_switch, basket_sneaking, confirm_shaming, cookie_wall,
                           disguised_ads, drip_pricing, fake_discount, fake_scarcity, false_urgency,
                           forced_action, interface_interference, nagging, prechecked_optin,
                           preselected_tip, saas_billing, social_proof, subscription_trap,
                           trick_question)
from backend.rules.base import Detection, RuleContext

ALL_RULES: list[ModuleType] = [
    false_urgency, fake_scarcity, social_proof, confirm_shaming, forced_action, subscription_trap,
    interface_interference, bait_and_switch, drip_pricing, basket_sneaking, disguised_ads, nagging,
    trick_question, saas_billing, prechecked_optin, preselected_tip, auto_renew, fake_discount,
    cookie_wall,
]


def run_rules(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    """Run every rule; a crashing rule is skipped so one bug cannot break the whole analysis."""
    detections: list[Detection] = []
    for rule in ALL_RULES:
        try:
            detections.extend(rule.detect(snapshot, ctx))
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[rules] {rule.__name__} failed: {exc}")
    return detections
