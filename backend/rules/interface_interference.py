"""CCPA 6 Interface Interference: one choice shouts, the other whispers.

Within a group of buttons shown together (same ``group_id``), if the 'decline / alternative' option
is much smaller (font size and visual weight) or hard to read (low WCAG contrast) compared with the
'accept' option, the design is steering the user.
"""

from __future__ import annotations

from backend.models import PageSnapshot
from backend.rules.base import (DECLINE_RE, Detection, RuleContext, buttons_by_group, contrast_ratio,
                                rx, visual_weight)

ALTERNATIVE = rx(r"\b(instead|reject|decline|no\b|not now|without|manage|basic|free plan|skip|later|cancel)")
FONT_RATIO = 1.4  # big font / small font
WEIGHT_RATIO = 3.0  # big visual weight / small visual weight
LOW_CONTRAST = 2.5  # below this the text is hard to see (WCAG AA wants 4.5)


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    found: list[Detection] = []
    for group in buttons_by_group(snapshot).values():
        if len(group) < 2 or len(group) > 6:  # menus / nav bars are not a single choice
            continue
        strong = max(group, key=visual_weight)
        for weak in group:
            if weak is strong:
                continue
            if not (DECLINE_RE.search(weak.text) or ALTERNATIVE.search(weak.text)):
                continue
            font_ratio = strong.font_size / max(weak.font_size, 1.0)
            weight_ratio = visual_weight(strong) / max(visual_weight(weak), 1.0)
            weak_contrast = contrast_ratio(weak.text_color, weak.bg_color)
            if font_ratio >= FONT_RATIO and (weight_ratio >= WEIGHT_RATIO or weak_contrast < LOW_CONTRAST):
                found.append(Detection(
                    "INTERFACE_INTERFERENCE", f"'{strong.text}' vs '{weak.text}'", weak.id, 0.85, "confirmed",
                    note=(f"'{strong.text}' is {font_ratio:.1f}x larger text than '{weak.text}'"
                          f" (contrast of the smaller option: {weak_contrast:.1f}:1).")))
    return found
