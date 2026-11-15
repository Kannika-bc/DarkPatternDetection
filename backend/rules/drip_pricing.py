"""CCPA 8 Drip Pricing: extra fees revealed late in the purchase.

* Single page: price rows labelled with non-standard fees (platform, convenience, handling,
  packaging, surge, small-cart, transaction, booking/service charge). Delivery, shipping and taxes
  are normal and ignored.
* Cross-page: if a lower price for this site was seen earlier (``previous_prices``) the finding is
  *confirmed*: the user really was shown a lower price first.
"""

from __future__ import annotations

from backend.models import PageSnapshot, Price
from backend.rules.base import Detection, RuleContext, rx

FEE = rx(r"\b(platform|convenience|handling|packaging|packing|service|surge|small cart|transaction|booking|"
         r"processing|gateway|internet handling|order processing)\b.{0,20}\b(fee|fees|charge|charges)\b")
NORMAL = rx(r"\b(delivery|shipping|tax|taxes|gst|vat|duty)\b")
TOTAL = rx(r"\b(total|to pay|amount payable|grand total|you pay)\b")


def fee_lines(snapshot: PageSnapshot) -> list[Price]:
    """Prices whose row label is a non-standard fee (deduplicated by row text)."""
    seen: set[str] = set()
    out: list[Price] = []
    for p in snapshot.prices:
        ctx = p.context or ""
        if p.struck_through or not p.value or ctx in seen:
            continue
        if FEE.search(ctx) and not NORMAL.search(ctx) and not TOTAL.search(ctx) and len(ctx) < 80:
            seen.add(ctx)
            out.append(p)
    return out


def page_total(snapshot: PageSnapshot) -> float | None:
    """Last price whose row says 'Total' / 'To pay' (bills usually end with the total)."""
    totals = [p.value for p in snapshot.prices if p.value and TOTAL.search(p.context or "") and len(p.context or "") < 80]
    return totals[-1] if totals else None


def detect(snapshot: PageSnapshot, ctx: RuleContext) -> list[Detection]:
    fees = fee_lines(snapshot)
    if not fees:
        return []
    names = "; ".join((f.context or f.raw_text) for f in fees)
    extra = sum(f.value or 0 for f in fees)
    total = page_total(snapshot)
    earlier = [pp for pp in snapshot.previous_prices if pp.value]
    if earlier and total and total > earlier[0].value:
        first = earlier[0]
        note = (f"Earlier on this site you saw {first.label} for {first.value:,.0f}; the total is now "
                f"{total:,.0f} after extra fees of {extra:,.0f}.")
        return [Detection("DRIP_PRICING", names, fees[0].id, 0.9, "confirmed", note=note)]
    conf = 0.8 if len(fees) >= 2 else 0.6
    return [Detection("DRIP_PRICING", names, fees[0].id, conf,
                      note=f"{len(fees)} extra fee(s) adding {extra:,.0f} appear only on this page.")]
