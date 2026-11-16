"""Merge rule detections and ML predictions into final Findings.

Steps:
1. Deduplicate rule hits (same type + same element, or same type where one text contains the other).
2. ML support: if the ML model also thinks the evidence text is a dark pattern, raise confidence.
3. ML-only findings: segments no rule caught but the model is very sure about (source="ml").
4. Attach CCPA reference, severity, fixable flag and a plain-language explanation.
5. Trust score (100 = no dark patterns found).
"""

from __future__ import annotations

import re
from typing import Optional, Protocol

from backend.ccpa import explanation_for, info_for
from backend.models import Finding, PageSnapshot
from backend.rules.base import Detection

ML_ONLY_THRESHOLD = 0.97  # the model must be very sure before adding a finding on its own
ML_SUPPORT_THRESHOLD = 0.5

_WORDS = re.compile(r"[A-Za-z]{2,}")

SEVERITY_WEIGHT = {"high": 15.0, "medium": 10.0, "low": 5.0}


class TextClassifier(Protocol):
    def predict(self, texts: list[str]) -> list[tuple[str, float]]: ...

    def predict_category(self, texts: list[str]) -> list[Optional[str]]: ...


# ML dataset categories -> our pattern types
# Only the narrow, well-defined categories are mapped to one pattern type. "Misdirection" and
# "Obstruction" cover several CCPA patterns, so ML-only hits there are reported as generic
# "suspicious wording" (with the category in the explanation) instead of guessing a CCPA number.
CATEGORY_TO_TYPE = {
    "urgency": "FALSE_URGENCY", "scarcity": "FAKE_SCARCITY", "social proof": "FAKE_SOCIAL_PROOF",
}


def _dedupe(detections: list[Detection]) -> list[Detection]:
    kept: list[Detection] = []
    for d in sorted(detections, key=lambda d: (d.status != "confirmed", -d.confidence)):
        duplicate = False
        for k in kept:
            if k.type != d.type:
                continue
            same_el = d.element_id is not None and d.element_id == k.element_id
            overlap = d.text and k.text and (d.text in k.text or k.text in d.text)
            if same_el or overlap:
                # Keep the strongest status/confidence, but show the more informative (longer) evidence,
                # e.g. "Lightning deal ends in 14:55" instead of just the timer "14:55".
                if len(d.text) > len(k.text):
                    k.text, k.element_id = d.text, d.element_id or k.element_id
                if d.note and d.note not in k.note:
                    k.note = (k.note + " " + d.note).strip()
                duplicate = True
                break
        if not duplicate:
            kept.append(d)
    return kept


def _apply_ml(detections: list[Detection], snapshot: PageSnapshot, clf: Optional[TextClassifier]) -> list[Detection]:
    if clf is None:
        return detections
    # 1) support existing rule hits
    if detections:
        preds = clf.predict([d.text for d in detections])
        for d, (label, prob) in zip(detections, preds):
            if label == "dark" and prob >= ML_SUPPORT_THRESHOLD:
                d.confidence = min(0.99, d.confidence + 0.1 * prob)
                d.note = (d.note + " The ML model agrees.").strip()
    # 2) ML-only findings on segments no rule flagged
    covered = {d.element_id for d in detections}
    # Only real sentences: at least 4 words of letters (prices / labels like "Item total" are skipped).
    candidates = [s for s in snapshot.segments
                  if s.id not in covered and len(s.text) <= 200 and len(_WORDS.findall(s.text)) >= 4]
    if candidates:
        preds = clf.predict([s.text for s in candidates])
        sure = [(s, p) for s, (label, p) in zip(candidates, preds) if label == "dark" and p >= ML_ONLY_THRESHOLD]
        if sure:
            cats = clf.predict_category([s.text for s, _ in sure])
            for (seg, prob), cat in zip(sure, cats):
                ptype = CATEGORY_TO_TYPE.get((cat or "").lower(), "ML_SUSPICIOUS_TEXT")
                detections.append(Detection(ptype, seg.text, seg.id, round(prob * 0.8, 3), source="ml",
                                            note=f"Flagged by the ML text classifier ({prob:.0%} sure, "
                                                 f"category: {cat or 'unknown'})."))
    return detections


def to_findings(detections: list[Detection], page_url: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, d in enumerate(detections, start=1):
        info = info_for(d.type)
        explanation = explanation_for(d.type)
        if d.note:
            explanation = f"{d.note} {explanation}"
        findings.append(Finding(
            id=f"f{i}", type=d.type, ccpa_ref=info.ccpa_ref, text=d.text[:300], element_id=d.element_id,
            confidence=round(min(max(d.confidence, 0.0), 1.0), 3), status=d.status, source=d.source,
            severity=info.severity, fixable=info.fixable, explanation=explanation, page_url=page_url,
        ))
    return findings


def merge(detections: list[Detection], snapshot: PageSnapshot, clf: Optional[TextClassifier] = None) -> list[Finding]:
    merged = _dedupe(detections)
    merged = _apply_ml(merged, snapshot, clf)
    merged.sort(key=lambda d: (-SEVERITY_WEIGHT[info_for(d.type).severity], -d.confidence))
    return to_findings(merged, snapshot.url)


def trust_score(findings: list[Finding]) -> int:
    """100 minus a penalty per finding (bigger for severe and confirmed findings)."""
    penalty = 0.0
    for f in findings:
        factor = 1.0 if f.status == "confirmed" else 0.7
        penalty += SEVERITY_WEIGHT[f.severity] * f.confidence * factor
    return int(max(0, min(100, round(100 - penalty))))
