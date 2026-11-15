"""Unit tests: each rule fires on a dark example and stays silent on an honest one."""

from backend.rules import (auto_renew, bait_and_switch, basket_sneaking, confirm_shaming, cookie_wall,
                           disguised_ads, drip_pricing, fake_discount, fake_scarcity, false_urgency,
                           forced_action, interface_interference, nagging, prechecked_optin,
                           preselected_tip, saas_billing, social_proof, subscription_trap, trick_question)
from backend.rules.base import RuleContext, contrast_ratio
from tests.helpers import button, price, snap

CTX = RuleContext()


def types(rule, s):
    return [d.type for d in rule.detect(s, CTX)]


def cb(id, label, checked=True, type="checkbox", group=None, group_label=None, required=False):
    return {"id": id, "type": type, "checked": checked, "label": label, "group": group,
            "group_label": group_label, "required": required}


# ---------------------------------------------------------------- text rules
def test_false_urgency_text_and_timer():
    assert types(false_urgency, snap(segments=["Hurry! Deal ends in 10 minutes"])) == ["FALSE_URGENCY"]
    s = snap(timers=[{"id": "t", "raw_text": "14:59", "seconds_left": 899, "reset_on_reload": True}])
    d = false_urgency.detect(s, CTX)[0]
    assert d.status == "confirmed" and d.confidence > 0.9


def test_false_urgency_ignores_fixed_dates():
    assert types(false_urgency, snap(segments=["Festive sale price valid until 31 December 2026."])) == []


def test_scarcity():
    assert types(fake_scarcity, snap(segments=["Only 2 left in stock"])) == ["FAKE_SCARCITY"]
    assert types(fake_scarcity, snap(segments=["In stock"])) == []


def test_social_proof():
    assert types(social_proof, snap(segments=["27 people are viewing this right now"])) == ["FAKE_SOCIAL_PROOF"]
    assert types(social_proof, snap(segments=["★ 4.3 from 2,140 verified ratings"])) == []


def test_confirm_shaming():
    s = snap(buttons=[button("b1", "No thanks, I prefer paying full price")])
    assert types(confirm_shaming, s) == ["CONFIRM_SHAMING"]
    assert types(confirm_shaming, snap(buttons=[button("b1", "No thanks")])) == []


def test_forced_action():
    assert types(forced_action, snap(segments=["Download the app to continue browsing"])) == ["FORCED_ACTION"]
    assert types(forced_action, snap(segments=["Our app can track prices. Using it is optional."])) == []


def test_subscription_trap():
    s = snap(segments=["To end your membership, please call 1800-000-0000. Memberships cannot be cancelled online."])
    assert types(subscription_trap, s) == ["SUBSCRIPTION_TRAP"]
    assert types(subscription_trap, snap(segments=["You can cancel online at any time from this page."])) == []


def test_saas_billing():
    bad = "After your trial ends you will be automatically charged ₹649/month. No reminder will be sent."
    good = "Try it free for 7 days. We'll email you before the trial ends; you will be charged only if you choose."
    assert types(saas_billing, snap(segments=[bad])) == ["SAAS_BILLING"]
    assert types(saas_billing, snap(segments=[good])) == []


def test_basket_sneaking():
    assert types(basket_sneaking, snap(segments=["Seat assurance (auto-added)"])) == ["BASKET_SNEAKING"]
    assert types(basket_sneaking, snap(segments=["Add to cart"])) == []


def test_disguised_ad_only_when_label_is_fine_print():
    tiny = {"id": "s1", "tag": "p", "text": "Finance · 3 min read Ad", "is_visible": True, "fine_print": "Ad"}
    big = {"id": "s2", "tag": "p", "text": "ADVERTISEMENT", "is_visible": True, "fine_print": None}
    assert types(disguised_ads, snap(segments=[tiny])) == ["DISGUISED_AD"]
    assert types(disguised_ads, snap(segments=[big])) == []


# ---------------------------------------------------------------- checkbox rules
def test_prechecked_optin():
    assert types(prechecked_optin, snap(checkboxes=[cb("c", "Send me offers by SMS")])) == ["PRECHECKED_OPTIN"]
    assert types(prechecked_optin, snap(checkboxes=[cb("c", "Send me offers", checked=False)])) == []
    assert types(prechecked_optin, snap(checkboxes=[cb("c", "Remember me")])) == []
    assert types(prechecked_optin, snap(checkboxes=[cb("c", "I agree to the Terms", required=True)])) == []


def test_preselected_tip_radio_group():
    opts = [cb("r0", "No tip", False, "radio", "tip", "Tip your delivery partner"),
            cb("r1", "Rs 20", True, "radio", "tip", "Tip your delivery partner")]
    assert types(preselected_tip, snap(checkboxes=opts)) == ["PRESELECTED_TIP"]
    opts[1]["checked"] = False
    assert types(preselected_tip, snap(checkboxes=opts)) == []


def test_preselected_donation_checkbox_not_double_counted():
    s = snap(checkboxes=[cb("c", "Donate Rs 3 to the Meal Fund")])
    assert types(preselected_tip, s) == ["PRESELECTED_TIP"]
    assert types(prechecked_optin, s) == []


def test_auto_renew():
    assert types(auto_renew, snap(checkboxes=[cb("c", "Auto-renew every month")])) == ["AUTO_RENEW"]
    assert types(auto_renew, snap(checkboxes=[cb("c", "Renew automatically", checked=False)])) == []


def test_trick_question():
    s = snap(checkboxes=[cb("c", "Uncheck this box if you do not wish to not receive offers")])
    assert types(trick_question, s) == ["TRICK_QUESTION"]
    assert types(trick_question, snap(checkboxes=[cb("c", "Email me offers. You can unsubscribe at any time.")])) == []


# ---------------------------------------------------------------- price rules
def _norm(s):
    from backend.analyzer import _normalise_prices
    _normalise_prices(s)
    return s


def test_drip_pricing_single_page_and_cross_page():
    rows = [price("p1", "Rs 249", "Item total Rs 249"), price("p2", "Rs 15", "Platform fee Rs 15"),
            price("p3", "Rs 25", "Packaging charges Rs 25"), price("p4", "Rs 289", "To pay Rs 289")]
    d = drip_pricing.detect(_norm(snap(prices=rows)), CTX)
    assert [x.type for x in d] == ["DRIP_PRICING"] and d[0].status == "unverified"
    s = _norm(snap(prices=rows, previous_prices=[{"label": "Biryani", "value": 249.0, "currency": "INR"}]))
    assert drip_pricing.detect(s, CTX)[0].status == "confirmed"


def test_delivery_fee_is_not_drip():
    rows = [price("p1", "₹1,499", "Item total ₹1,499"), price("p2", "₹40", "Delivery fee ₹40")]
    assert drip_pricing.detect(_norm(snap(prices=rows)), CTX) == []


def test_bait_and_switch_cross_page():
    s = _norm(snap(prices=[price("p1", "₹1,799", "Boltwave X2 Wireless Earbuds Qty 1 ₹1,799")],
                   previous_prices=[{"label": "Boltwave X2 Wireless Earbuds", "value": 1499.0, "currency": "INR"}]))
    d = bait_and_switch.detect(s, CTX)
    assert d and d[0].status == "confirmed"
    s.previous_prices[0].value = 1799.0
    assert bait_and_switch.detect(s, CTX) == []


def test_fake_discount():
    ctx = "₹14,999 ₹1,499 90% off"
    s = _norm(snap(prices=[price("a", "₹14,999", ctx, struck=True), price("b", "₹1,499", ctx)]))
    assert types(fake_discount, s) == ["FAKE_DISCOUNT"]
    ctx2 = "₹1,799 ₹1,499 17% off"
    s2 = _norm(snap(prices=[price("a", "₹1,799", ctx2, struck=True), price("b", "₹1,499", ctx2)]))
    assert types(fake_discount, s2) == []


# ---------------------------------------------------------------- button / popup rules
def test_contrast_ratio():
    assert round(contrast_ratio("rgb(0, 0, 0)", "rgb(255, 255, 255)")) == 21
    assert contrast_ratio("rgb(195, 198, 202)", "rgb(255, 255, 255)") < 2


def test_interface_interference():
    big = button("yes", "Accept all & continue", w=300, h=60, fs=19.2)
    tiny = button("no", "reject", w=30, h=12, fs=11.2, color="rgb(195, 198, 202)", bg="rgb(255, 255, 255)")
    assert types(interface_interference, snap(buttons=[big, tiny])) == ["INTERFACE_INTERFERENCE"]
    equal = button("no", "Reject all", w=120, h=40, fs=16)
    assert types(interface_interference, snap(buttons=[button("yes", "Accept all"), equal])) == []


def test_cookie_wall():
    popup = {"id": "p", "text": "We use cookies to personalise offers.", "is_blocking": False}
    s = snap(popups=[popup], buttons=[button("a", "Accept all", popup="p"), button("m", "Manage options", popup="p")])
    assert types(cookie_wall, s) == ["COOKIE_WALL"]
    s2 = snap(popups=[popup], buttons=[button("a", "Accept all", popup="p"), button("r", "Reject all", popup="p")])
    assert types(cookie_wall, s2) == []


def test_nagging():
    popup = {"id": "p", "text": "Enjoying us? Rate us 5 stars!", "is_blocking": True}
    s = snap(popups=[popup], buttons=[button("a", "Rate now", popup="p"), button("l", "Maybe later", popup="p")])
    assert types(nagging, s) == ["NAGGING"]
    popup2 = {**popup, "times_shown": 3}
    s2 = snap(popups=[popup2], buttons=[button("a", "Rate now", popup="p"), button("l", "Maybe later", popup="p")])
    assert nagging.detect(s2, CTX)[0].status == "confirmed"
    s3 = snap(popups=[popup], buttons=[button("a", "Rate now", popup="p"), button("n", "No thanks", popup="p")])
    assert types(nagging, s3) == []
