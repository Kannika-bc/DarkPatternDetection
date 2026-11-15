import pytest

from backend.prices import parse_price, parse_prices


@pytest.mark.parametrize("text,value,currency", [
    ("₹1,499", 1499.0, "INR"),
    ("Rs 249", 249.0, "INR"),
    ("Rs. 18,750.00", 18750.0, "INR"),
    ("INR 4,610", 4610.0, "INR"),
    ("₹1,00,000", 100000.0, "INR"),  # Indian digit grouping
    ("US$ 389", 389.0, "USD"),
    ("$19.99", 19.99, "USD"),
    ("€412.50", 412.5, "EUR"),
    ("£1,240.00", 1240.0, "GBP"),
    ("499 INR", 499.0, "INR"),
])
def test_formats(text, value, currency):
    p = parse_price(text)
    assert p is not None and p.value == value and p.currency == currency


def test_several_prices_in_one_text():
    assert [p.value for p in parse_prices("MRP ₹14,999 now ₹1,499")] == [14999.0, 1499.0]


@pytest.mark.parametrize("text", ["30 h battery", "Bluetooth 5.3", "4 screens", "hours 25", "", "Delivery FREE"])
def test_not_prices(text):
    assert parse_price(text) is None
