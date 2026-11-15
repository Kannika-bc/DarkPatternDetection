"""The JSON Schema and the Pydantic models must describe exactly the same PageSnapshot."""

import json
from pathlib import Path

import jsonschema

from backend.models import PageSnapshot
from tests.helpers import button, price, snap

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "shared" / "page_snapshot.schema.json").read_text(encoding="utf-8"))

NESTED = {
    "segments": "Segment", "checkboxes": "Checkbox", "buttons": "Button", "prices": "Price",
    "popups": "Popup", "timers": "Timer", "previous_prices": "PreviousPrice",
}


def test_top_level_fields_match():
    assert set(SCHEMA["properties"]) == set(PageSnapshot.model_fields)
    assert set(SCHEMA["required"]) == {n for n, f in PageSnapshot.model_fields.items() if f.is_required()}


def test_nested_fields_match():
    pyd = PageSnapshot.model_json_schema()["$defs"]
    for field, model_name in NESTED.items():
        json_props = set(SCHEMA["properties"][field]["items"]["properties"])
        assert json_props == set(pyd[model_name]["properties"]), field


def test_pydantic_output_validates_against_json_schema():
    s = snap(segments=["Only 2 left!"], buttons=[button("b1", "Buy")], prices=[price("p1", "₹1,499", "Price ₹1,499")],
             timers=[{"id": "t1", "raw_text": "10:00", "seconds_left": 600}],
             previous_prices=[{"label": "Earbuds", "value": 1499.0, "currency": "INR", "url": None}])
    jsonschema.validate(json.loads(s.model_dump_json()), SCHEMA)


def test_unknown_field_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        snap(password="secret")
