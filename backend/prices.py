"""Universal price parser.

Turns strings like "₹1,499", "Rs. 18,750.00", "INR 4,610", "US$ 389", "€412.50", "£1,240.00" into
``ParsedPrice(value, currency)``. Handles Indian (1,00,000) and western (100,000) digit grouping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Currency marker -> ISO code. Longer markers first so "US$" wins over "$".
_CURRENCIES: list[tuple[str, str]] = [
    ("US$", "USD"), ("USD", "USD"), ("INR", "INR"), ("RS.", "INR"), ("RS", "INR"), ("₹", "INR"),
    ("EUR", "EUR"), ("€", "EUR"), ("GBP", "GBP"), ("£", "GBP"), ("$", "USD"),
]

PRICE_PATTERN = re.compile(
    r"(?<![A-Za-z])(?P<cur>US\$|USD|INR|Rs\.?|₹|EUR|€|GBP|£|\$)\s?(?P<num>\d[\d,]*(?:\.\d+)?)"
    r"|(?P<num2>\d[\d,]*(?:\.\d+)?)\s?(?P<cur2>₹|€|£|INR|EUR|GBP|USD)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedPrice:
    value: float
    currency: str
    raw: str


def _currency_code(marker: str) -> Optional[str]:
    up = marker.upper()
    for key, code in _CURRENCIES:
        if up == key or up.rstrip(".") == key.rstrip("."):
            return code
    return None


def _to_number(num: str) -> Optional[float]:
    try:
        return float(num.replace(",", ""))
    except ValueError:
        return None


def parse_prices(text: str) -> list[ParsedPrice]:
    """Find every price in a piece of text."""
    out: list[ParsedPrice] = []
    for m in PRICE_PATTERN.finditer(text or ""):
        marker = m.group("cur") or m.group("cur2")
        num = m.group("num") or m.group("num2")
        value = _to_number(num)
        code = _currency_code(marker)
        if value is not None and code:
            out.append(ParsedPrice(value=value, currency=code, raw=m.group(0).strip()))
    return out


def parse_price(text: str) -> Optional[ParsedPrice]:
    """First price in the text, or None."""
    found = parse_prices(text)
    return found[0] if found else None
