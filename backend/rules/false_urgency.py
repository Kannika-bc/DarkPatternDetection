"""CCPA 1 False Urgency: 'hurry', 'deal ends in', countdown timers (fake if they reset on reload)."""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import Detection, RuleContext, rx
from backend.rules.text_rules import scan_segments

PATTERNS = [
    rx(r"\bhurry\b"),
    rx(r"\b(ends?|ending|expires?|expiring) (in|soon|today|tonight)\b"),
    rx(r"\bclosing soon\b"),
    rx(r"\blast chance\b"),
    rx(r"\bmiss out\b"),
    rx(r"\blimited[- ]time (offer|deal)\b"),
    rx(r"\bprices? (may|will) (go up|increase|rise)\b"),
    rx(r"\b(fares?|prices?|offer|deal)s? (locked|held|reserved) for\b"),
    rx(r"\b(in|within) the next \d+ (minutes?|mins?|hours?|seconds?)\b"),
    rx(r"\b(lightning|flash) (deal|sale)\b"),
    rx(r"\bact (now|fast)\b"),
]
# A fixed calendar date ("valid until 31 December 2026") is honest information, not false urgency.
EXCLUDE = [rx(r"\b(valid|available) (until|till) \d{1,2} \w+ \d{4}\b")]


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    found = scan_segments(snapshot, "FALSE_URGENCY", PATTERNS, exclude=EXCLUDE, confidence=0.75)
    for timer in snapshot.timers:
        if timer.reset_on_reload:
            found.append(Detection(
                "FALSE_URGENCY", timer.raw_text, timer.id, 0.95, "confirmed",
                note="The countdown restarted when the page was reloaded, so the deadline is fake."))
        else:
            found.append(Detection("FALSE_URGENCY", timer.raw_text, timer.id, 0.7,
                                   note="Countdown timer creating time pressure."))
    return found
