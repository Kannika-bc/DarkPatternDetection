"""Tiny builders for synthetic PageSnapshots used by the unit tests."""

from __future__ import annotations

from typing import Any

from backend.models import PageSnapshot


def snap(**parts: Any) -> PageSnapshot:
    """snap(segments=[...], checkboxes=[...]) -> PageSnapshot with sensible defaults."""
    base: dict[str, Any] = {
        "url": "http://example.test/page", "title": "Test page", "collected_at": "2026-01-01T00:00:00Z",
        "collector": "playwright", "segments": [], "checkboxes": [], "buttons": [], "prices": [],
        "popups": [], "timers": [], "previous_prices": [],
    }
    base.update(parts)
    # allow short-hand: segments=["text", ...]
    base["segments"] = [
        s if isinstance(s, dict) else {"id": f"s{i}", "tag": "p", "text": s, "is_visible": True}
        for i, s in enumerate(base["segments"])
    ]
    return PageSnapshot.model_validate(base)


def button(id: str, text: str, *, w: float = 120, h: float = 40, fs: float = 16, group: str | None = "g1",
           color: str = "rgb(255, 255, 255)", bg: str = "rgb(37, 99, 235)", popup: str | None = None) -> dict:
    return {"id": id, "text": text, "width": w, "height": h, "font_size": fs, "bg_color": bg, "text_color": color,
            "in_popup": popup is not None, "kind": "button", "group_id": group, "popup_id": popup}


def price(id: str, raw: str, context: str, struck: bool = False) -> dict:
    return {"id": id, "raw_text": raw, "value": None, "currency": None, "struck_through": struck, "context": context}
