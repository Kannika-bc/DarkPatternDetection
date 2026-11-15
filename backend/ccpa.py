"""Mapping from DarkLens pattern types to the CCPA 2023 guidelines.

CCPA = Central Consumer Protection Authority (India), "Guidelines for Prevention and Regulation of
Dark Patterns, 2023". Annexure 1 lists 13 specified dark patterns. Extra patterns we detect that the
guidelines do not name separately get ``ccpa_ref=None`` and a ``related`` pointer to the closest one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PatternInfo:
    name: str
    ccpa_ref: Optional[int]
    severity: str  # low | medium | high
    fixable: bool  # can the extension undo it with one click?
    explanation: str  # plain language, shown to the user
    related: Optional[int] = None  # closest CCPA pattern for extras


CCPA_NAMES: dict[int, str] = {
    1: "False Urgency", 2: "Basket Sneaking", 3: "Confirm Shaming", 4: "Forced Action",
    5: "Subscription Trap", 6: "Interface Interference", 7: "Bait and Switch", 8: "Drip Pricing",
    9: "Disguised Advertisement", 10: "Nagging", 11: "Trick Question", 12: "SaaS Billing",
    13: "Rogue Malware",
}

PATTERNS: dict[str, PatternInfo] = {
    "FALSE_URGENCY": PatternInfo(
        "False Urgency", 1, "medium", False,
        "Creates pressure to buy quickly with a countdown or 'hurry' message. If the timer restarts "
        "when you reload, the deadline is fake. Take your time."),
    "BASKET_SNEAKING": PatternInfo(
        "Basket Sneaking", 2, "high", False,
        "Something you did not choose was added to your cart or bill. You are not obliged to pay for "
        "it; remove it before paying."),
    "CONFIRM_SHAMING": PatternInfo(
        "Confirm Shaming", 3, "low", False,
        "The 'no' option is worded to make you feel guilty or foolish. Declining is a normal choice."),
    "FORCED_ACTION": PatternInfo(
        "Forced Action", 4, "medium", False,
        "You are told you must do something unrelated (install an app, create an account, share data) "
        "to continue. CCPA lists this as a prohibited dark pattern."),
    "SUBSCRIPTION_TRAP": PatternInfo(
        "Subscription Trap", 5, "high", False,
        "Cancelling is made much harder than signing up (phone only, narrow hours, hidden option)."),
    "INTERFACE_INTERFERENCE": PatternInfo(
        "Interface Interference", 6, "medium", False,
        "The design hides or shrinks one choice (tiny, grey 'no') and pushes the other (huge, bright "
        "'yes'). Both choices should be equally visible."),
    "BAIT_AND_SWITCH": PatternInfo(
        "Bait and Switch", 7, "high", False,
        "The price or product shown earlier is not what you are being charged for now."),
    "DRIP_PRICING": PatternInfo(
        "Drip Pricing", 8, "high", False,
        "Extra fees are revealed only late in the purchase, so the final price is higher than the "
        "price you were first shown."),
    "DISGUISED_AD": PatternInfo(
        "Disguised Advertisement", 9, "medium", False,
        "This looks like normal content (news, review) but is an advertisement with a tiny or hidden "
        "label."),
    "NAGGING": PatternInfo(
        "Nagging", 10, "low", False,
        "A request (rate us, notifications, newsletter) keeps coming back and offers only 'later', "
        "never a permanent 'no'."),
    "TRICK_QUESTION": PatternInfo(
        "Trick Question", 11, "medium", False,
        "Confusing wording (double negatives) makes it hard to tell what ticking the box means. Read "
        "it carefully; DarkLens shows a plain-language version."),
    "SAAS_BILLING": PatternInfo(
        "SaaS Billing", 12, "high", False,
        "A free trial turns into a paid subscription automatically, without a clear reminder. Note the "
        "end date or avoid giving card details."),
    "PRECHECKED_OPTIN": PatternInfo(
        "Pre-checked opt-in", None, "medium", True,
        "This box was ticked for you. Consent must be your own choice: untick it if you do not want it.",
        related=2),
    "PRESELECTED_TIP": PatternInfo(
        "Pre-selected tip/donation", None, "medium", True,
        "A tip or donation was selected for you by default. It should be your choice; DarkLens can "
        "switch it to 'no tip'.", related=2),
    "FAKE_SCARCITY": PatternInfo(
        "Fake scarcity", None, "low", False,
        "Claims of very low stock push you to buy now. Such claims usually cannot be verified.",
        related=1),
    "FAKE_SOCIAL_PROOF": PatternInfo(
        "Fake social proof", None, "low", False,
        "'X people are viewing/bought this' messages are often made up or random.", related=1),
    "FAKE_DISCOUNT": PatternInfo(
        "Fake discount", None, "medium", False,
        "The 'original' price looks inflated so the discount seems huge. Compare prices elsewhere.",
        related=7),
    "COOKIE_WALL": PatternInfo(
        "Cookie wall", None, "medium", False,
        "You cannot easily refuse cookies (no reject option, or content is blocked until you accept).",
        related=4),
    "AUTO_RENEW": PatternInfo(
        "Auto-renew on by default", None, "medium", True,
        "Automatic renewal was switched on for you. DarkLens can switch it off.", related=12),
    "ML_SUSPICIOUS_TEXT": PatternInfo(
        "Suspicious wording (ML)", None, "low", False,
        "Our machine-learning model thinks this text uses persuasive or deceptive wording."),
}


def info_for(pattern_type: str) -> PatternInfo:
    """Metadata for a pattern type (falls back to a generic entry)."""
    return PATTERNS.get(pattern_type, PATTERNS["ML_SUSPICIOUS_TEXT"])


def explanation_for(pattern_type: str) -> str:
    """Plain-language explanation including the CCPA reference."""
    info = info_for(pattern_type)
    if info.ccpa_ref:
        ref = f"CCPA Guidelines 2023, pattern {info.ccpa_ref} ({CCPA_NAMES[info.ccpa_ref]})."
    elif info.related:
        ref = f"Not listed separately by CCPA; closest is pattern {info.related} ({CCPA_NAMES[info.related]})."
    else:
        ref = ""
    return f"{info.explanation} {ref}".strip()
