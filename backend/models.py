"""Pydantic data models for DarkLens.

These models mirror ``shared/page_snapshot.schema.json`` exactly (``extra="forbid"`` means an
unknown field is an error, just like ``additionalProperties: false`` in the JSON Schema).
``tests/test_models.py`` checks that the two stay in sync.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    """Base class: reject unknown fields so both collectors must follow the schema."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- PageSnapshot


class Segment(_Strict):
    id: str
    tag: str
    text: str = Field(max_length=300)
    is_visible: bool
    font_size: Optional[float] = None
    fine_print: Optional[str] = None


class Checkbox(_Strict):
    id: str
    type: Literal["checkbox", "radio"]
    checked: bool
    label: str
    group: Optional[str] = None
    group_label: Optional[str] = None
    required: bool = False


class Button(_Strict):
    id: str
    text: str
    width: float
    height: float
    font_size: float
    bg_color: str
    text_color: str
    in_popup: bool
    kind: Literal["button", "link"] = "button"
    group_id: Optional[str] = None
    popup_id: Optional[str] = None


class Price(_Strict):
    id: str
    raw_text: str
    value: Optional[float]
    currency: Optional[str]
    struck_through: bool
    context: Optional[str] = None


class Popup(_Strict):
    id: str
    text: str
    is_blocking: bool
    times_shown: int = 1


class Timer(_Strict):
    id: str
    raw_text: str
    seconds_left: Optional[int]
    reset_on_reload: Optional[bool] = None


class PreviousPrice(_Strict):
    label: str
    value: float
    currency: Optional[str] = None
    url: Optional[str] = None


class SnapshotStats(_Strict):
    elements_scanned: Optional[int] = None
    duration_ms: Optional[float] = None


class PageSnapshot(_Strict):
    """Everything DarkLens knows about one page. Same format from both collectors."""

    url: str
    title: str
    collected_at: str
    collector: Literal["extension", "playwright"]
    segments: list[Segment] = Field(max_length=2000)
    checkboxes: list[Checkbox]
    buttons: list[Button]
    prices: list[Price]
    popups: list[Popup]
    timers: list[Timer]
    previous_prices: list[PreviousPrice] = Field(default_factory=list)
    stats: Optional[SnapshotStats] = None


# --------------------------------------------------------------------------- Findings

Severity = Literal["low", "medium", "high"]
Status = Literal["confirmed", "unverified"]
Source = Literal["rule", "ml", "agent"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Finding(BaseModel):
    """One detected dark pattern."""

    id: str
    type: str  # e.g. "FALSE_URGENCY" (see backend/ccpa.py for the full list)
    ccpa_ref: Optional[int] = None  # 1..13 from the CCPA 2023 guidelines, None for extras
    text: str  # evidence text shown to the user
    element_id: Optional[str] = None  # data-darklens-id of the element, if any
    confidence: float = Field(ge=0.0, le=1.0)
    status: Status = "unverified"
    source: Source = "rule"
    severity: Severity = "medium"
    fixable: bool = False
    explanation: str = ""
    page_url: str = ""
    timestamp: str = Field(default_factory=now_iso)


class PriceObservation(BaseModel):
    """Main product price seen on a page; the extension/agent remember it as previous_prices."""

    label: str
    value: float
    currency: Optional[str] = None
    url: Optional[str] = None


class AnalyzeResponse(BaseModel):
    url: str
    page_type: str
    trust_score: int = Field(ge=0, le=100)
    findings: list[Finding]
    price_observation: Optional[PriceObservation] = None
    duration_ms: float = 0.0
