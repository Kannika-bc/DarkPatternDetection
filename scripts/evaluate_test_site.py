"""Evaluate DarkLens end to end on the test site against test-site/ground-truth.json.

For every page: open it in Playwright, wait for delayed popups, collect a PageSnapshot (with the
timer-reload check), analyse it, and match each finding to the planted patterns:
a finding is correct if its type is the planted type (or an accepted alternative) AND its element
is inside / contains the planted element. Pages of a site are visited in journey order (product
page first) and price observations are passed on as ``previous_prices``, exactly like the extension.

Run with the test site served on port 8090:
    python -m http.server 8090 --directory test-site
    python -m scripts.evaluate_test_site            # -> docs/report/evaluation.md
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from backend.analyzer import analyze
from backend.models import PreviousPrice
from collector.playwright_collector import check_timer_resets, collect_snapshot, settle

ROOT = Path(__file__).resolve().parents[1]
TRUTH = json.loads((ROOT / "test-site" / "ground-truth.json").read_text(encoding="utf-8"))
OUT = ROOT / "docs" / "report" / "evaluation.md"

# JavaScript that tells us whether a finding's element and a planted element overlap.
MATCH_JS = """
([elementId, items]) => {
  const el = window.DarkLensCollector.elementFor(elementId);
  if (!el) return [];
  const resolve = (it) => {
    if (it.context === "main") return document.querySelector(it.selector);
    if (it.context.shadowHost) {
      const host = document.querySelector(it.context.shadowHost);
      return host && host.shadowRoot ? host.shadowRoot.querySelector(it.selector) : null;
    }
    if (it.context.iframe) {
      const name = it.context.iframe.split("/").pop();
      const frame = document.querySelector('iframe[src$="' + name + '"]');
      return frame && frame.contentDocument ? frame.contentDocument.querySelector(it.selector) : null;
    }
    return null;
  };
  return items.filter((it) => { const p = resolve(it); return p && (p.contains(el) || el.contains(p)); })
              .map((it) => it.id);
}
"""


def accepted_types(item: dict) -> set[str]:
    return {item["type"], *item.get("alsoAccept", [])}


def evaluate(settle_ms: int, use_ml: bool) -> dict:
    results: list[dict] = []
    history: dict[str, list[PreviousPrice]] = defaultdict(list)  # per site (category)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page: Page = browser.new_page(viewport={"width": 1280, "height": 900})
        for spec in TRUTH["pages"]:
            if spec["path"] == "news/ad-frame.html":
                continue  # only used inside news/article.html
            page.goto(f"http://localhost:8090/{spec['path']}")
            settle(page, settle_ms)
            snap = collect_snapshot(page)
            check_timer_resets(page, snap)
            # The reload created a fresh page, so re-collect (element ids must match the live page)
            # and copy over the reset flags, timer by timer.
            resets = [t.reset_on_reload for t in snap.timers]
            settle(page, settle_ms)
            snap = collect_snapshot(page)
            for i, t in enumerate(snap.timers):
                t.reset_on_reload = resets[i] if i < len(resets) else None
            snap.previous_prices = list(history[spec["category"]])
            res = analyze(snap, use_ml=use_ml)
            if res.price_observation and not any(h.label == res.price_observation.label for h in history[spec["category"]]):
                history[spec["category"]].append(PreviousPrice(**res.price_observation.model_dump()))

            items = spec["findings"]
            negatives = [{"id": n["selector"], "selector": n["selector"], "context": "main", "type": n["looksLike"]}
                         for n in spec.get("hardNegatives", [])]
            matched_items: set[str] = set()
            finding_rows = []
            for f in res.findings:
                overlaps = page.evaluate(MATCH_JS, [f.element_id, items + negatives]) if f.element_id else []
                hits = [it["id"] for it in items if it["id"] in overlaps and f.type in accepted_types(it)]
                neg_hits = [n["id"] for n in negatives if n["id"] in overlaps]
                matched_items.update(hits)
                finding_rows.append({"type": f.type, "status": f.status, "source": f.source,
                                     "confidence": f.confidence, "text": f.text[:80], "correct": bool(hits),
                                     "hard_negative": neg_hits})
            results.append({
                "path": spec["path"], "category": spec["category"], "expected_page_type": spec["pageType"],
                "page_type": res.page_type, "trust_score": res.trust_score,
                "items": [{**it, "found": it["id"] in matched_items} for it in items],
                "findings": finding_rows,
            })
            print(f"{spec['path']:22} type={res.page_type:12} trust={res.trust_score:3} "
                  f"found {len(matched_items)}/{len(items)} planted, {sum(not r['correct'] for r in finding_rows)} false positive(s)")
        browser.close()
    return {"pages": results}


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def report(data: dict, use_ml: bool) -> str:
    pages = data["pages"]
    per_type: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0})
    per_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0})
    phase: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for pg in pages:
        for it in pg["items"]:
            key = "tp" if it["found"] else "fn"
            per_type[it["type"]][key] += 1
            per_cat[pg["category"]][key] += 1
            phase[it["phase"]][0] += int(it["found"])
            phase[it["phase"]][1] += 1
        for f in pg["findings"]:
            if not f["correct"]:
                per_type[f["type"]]["fp"] += 1
                per_cat[pg["category"]]["fp"] += 1
    tot_tp = sum(v["tp"] for v in per_type.values())
    tot_fn = sum(v["fn"] for v in per_type.values())
    tot_fp = sum(v["fp"] for v in per_type.values())
    P, R, F = _prf(tot_tp, tot_fp, tot_fn)
    pt_ok = sum(pg["page_type"] == pg["expected_page_type"] for pg in pages)
    clean = [pg for pg in pages if pg["category"] == "clean"]
    clean_fp = sum(len(pg["findings"]) for pg in clean)
    hard_total = sum(1 for _ in TRUTH["pages"] for _ in _.get("hardNegatives", []))
    hard_hit = {h for pg in clean for f in pg["findings"] for h in f["hard_negative"]}

    L = ["# Test-site evaluation", "",
         f"Generated by `python -m scripts.evaluate_test_site` (ML {'on' if use_ml else 'off'}). "
         "A finding counts as correct when its type matches the planted type (or an accepted "
         "alternative) and its element overlaps the planted element.", "",
         "## Overall", "",
         f"* Planted patterns found (recall): **{tot_tp}/{tot_tp + tot_fn} = {R:.1%}**",
         f"* Precision of findings: **{P:.1%}** ({tot_fp} false positives)",
         f"* F1: **{F:.3f}**",
         f"* False positives on the clean site: **{clean_fp}** across {len(clean)} pages "
         f"({len(hard_hit)}/{hard_total} hard negatives wrongly flagged)",
         f"* Page-type detector accuracy: **{pt_ok}/{len(pages)}**",
         "* Recall by phase: " + ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(phase.items())), "",
         "## Per pattern", "", "| Pattern | TP | FN | FP | Precision | Recall | F1 |", "|---|---|---|---|---|---|---|"]
    for t in sorted(per_type):
        v = per_type[t]
        p, r, f = _prf(v["tp"], v["fp"], v["fn"])
        L.append(f"| {t} | {v['tp']} | {v['fn']} | {v['fp']} | {p:.2f} | {r:.2f} | {f:.2f} |")
    L += ["", "## Per category", "", "| Category | TP | FN | FP | Precision | Recall | F1 |", "|---|---|---|---|---|---|---|"]
    for c in sorted(per_cat):
        v = per_cat[c]
        p, r, f = _prf(v["tp"], v["fp"], v["fn"])
        L.append(f"| {c} | {v['tp']} | {v['fn']} | {v['fp']} | {p:.2f} | {r:.2f} | {f:.2f} |")
    L += ["", "## Per page", ""]
    for pg in pages:
        L.append(f"### {pg['path']}  (page type: {pg['page_type']}, expected {pg['expected_page_type']}; trust score {pg['trust_score']})")
        for it in pg["items"]:
            L.append(f"* {'✅' if it['found'] else '❌'} planted {it['type']} `{it['selector']}` ({it['phase']}, {it['evidence']})")
        for f in pg["findings"]:
            if not f["correct"]:
                L.append(f"* ⚠️ false positive {f['type']} ({f['source']}, {f['confidence']:.2f}): \"{f['text']}\"")
        L.append("")
    missed = [(pg["path"], it) for pg in pages for it in pg["items"] if not it["found"]]
    if missed:
        L += ["## Why some planted patterns are missed", ""]
        for path, it in missed:
            why = it.get("notes", "")
            if it["evidence"] == "behaviour":
                why = "needs behaviour over time (e.g. the popup must re-appear after being closed); " + why
            L.append(f"* `{path}` {it['type']}: {why}".rstrip(": "))
        L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--settle-ms", type=int, default=5500, help="wait for delayed popups (nagging appears after 5 s)")
    ap.add_argument("--no-ml", action="store_true")
    a = ap.parse_args()
    data = evaluate(a.settle_ms, use_ml=not a.no_ml)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(report(data, not a.no_ml), encoding="utf-8")
    (OUT.parent / "evaluation.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
