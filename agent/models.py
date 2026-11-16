"""Pydantic models for the agent's audit report."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from backend.models import Finding, now_iso


class AuditStep(BaseModel):
    step: int
    url: str
    action: str  # what the agent did to get here ("open", "click 'Add to cart'", ...)
    reason: str = ""  # why (from the LLM or the fallback policy)
    page_type: str = ""
    trust_score: Optional[int] = None
    findings: int = 0
    note: str = ""  # guardrail messages, errors


class PriceChange(BaseModel):
    step: int
    url: str
    label: str
    value: float
    currency: Optional[str] = None
    kind: str  # "product" (first price seen) or "total" (bill total on cart/checkout)


class AuditFinding(Finding):
    step: int = 0


class CcpaReference(BaseModel):
    pattern: int
    name: str
    passage: str
    source: str = "summary"  # "summary" (our JSON) or the guideline PDF's file name


class AuditReport(BaseModel):
    url: str
    started_at: str = Field(default_factory=now_iso)
    finished_at: str = ""
    llm_used: bool = False
    model: Optional[str] = None
    stop_reason: str = ""
    steps: list[AuditStep] = Field(default_factory=list)
    findings: list[AuditFinding] = Field(default_factory=list)
    price_changes: list[PriceChange] = Field(default_factory=list)
    trust_score: int = 100
    summary: str = ""
    ccpa_references: list[CcpaReference] = Field(default_factory=list)
    log: list[str] = Field(default_factory=list)
