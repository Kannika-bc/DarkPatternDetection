"""Sanity-check test-site/ground-truth.json against the HTML pages.

Run from the repo root:  python test-site/check_ground_truth.py
Uses only the Python standard library. Exits with code 1 if any problem is found.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

SITE = Path(__file__).resolve().parent
ALLOWED_PAGE_TYPES = {"product", "cart", "checkout", "signup", "subscription", "article", "other"}
ALLOWED_PHASES = {"MVP", "V2"}
ALLOWED_EVIDENCE = {"text", "dom", "behaviour", "cross-page"}
ALLOWED_STATUS = {"confirmed", "unverified"}


def id_in_source(element_id: str, source: str) -> bool:
    """True if the id is set in HTML (id="x") or by JS (el.id = "x")."""
    pattern = rf'(\bid\s*=\s*["\']{re.escape(element_id)}["\'])|(\.id\s*=\s*["\']{re.escape(element_id)}["\'])'
    return re.search(pattern, source) is not None


def selector_id(selector: str) -> str | None:
    match = re.fullmatch(r"#([A-Za-z][\w-]*)", selector)
    return match.group(1) if match else None


def main() -> int:
    truth = json.loads((SITE / "ground-truth.json").read_text(encoding="utf-8"))
    ccpa_refs: dict[str, int | None] = truth["ccpaRefs"]
    errors: list[str] = []
    seen_ids: set[str] = set()
    type_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()

    listed_pages = {page["path"] for page in truth["pages"]}
    on_disk = {
        p.relative_to(SITE).as_posix()
        for p in SITE.rglob("*.html")
        if p.parent != SITE and "shared" not in p.parts
    }
    for missing in sorted(on_disk - listed_pages):
        errors.append(f"{missing}: HTML page not listed in ground-truth.json")

    for page in truth["pages"]:
        path = page["path"]
        file = SITE / path
        if not file.exists():
            errors.append(f"{path}: file does not exist")
            continue
        source = file.read_text(encoding="utf-8")
        if page["pageType"] not in ALLOWED_PAGE_TYPES:
            errors.append(f"{path}: unknown pageType {page['pageType']!r}")
        if page["category"] == "clean" and page["findings"]:
            errors.append(f"{path}: clean pages must have no findings")

        for f in page["findings"]:
            fid = f["id"]
            where = f"{path} [{fid}]"
            if fid in seen_ids:
                errors.append(f"{where}: duplicate finding id")
            seen_ids.add(fid)
            if f["type"] not in ccpa_refs:
                errors.append(f"{where}: unknown type {f['type']!r}")
            elif f["ccpaRef"] != ccpa_refs[f["type"]]:
                errors.append(f"{where}: ccpaRef {f['ccpaRef']} should be {ccpa_refs[f['type']]}")
            for other in f.get("alsoAccept", []):
                if other not in ccpa_refs:
                    errors.append(f"{where}: unknown alsoAccept type {other!r}")
            if f["phase"] not in ALLOWED_PHASES:
                errors.append(f"{where}: bad phase {f['phase']!r}")
            if f["evidence"] not in ALLOWED_EVIDENCE:
                errors.append(f"{where}: bad evidence {f['evidence']!r}")
            if f["expectedStatus"] not in ALLOWED_STATUS:
                errors.append(f"{where}: bad expectedStatus {f['expectedStatus']!r}")

            element_id = selector_id(f["selector"])
            if element_id is None:
                errors.append(f"{where}: selector must be a simple '#id', got {f['selector']!r}")
                continue

            context = f["context"]
            target_source = source
            if isinstance(context, dict) and "iframe" in context:
                frame_path = context["iframe"]
                frame_file = SITE / frame_path
                if not frame_file.exists():
                    errors.append(f"{where}: iframe file {frame_path} missing")
                    continue
                frame_src = Path(frame_path).name
                if f'src="{frame_src}"' not in source:
                    errors.append(f"{where}: page does not embed iframe {frame_path}")
                target_source = frame_file.read_text(encoding="utf-8")
            elif isinstance(context, dict) and "shadowHost" in context:
                host_id = selector_id(context["shadowHost"])
                if host_id is None or not id_in_source(host_id, source):
                    errors.append(f"{where}: shadow host {context['shadowHost']} not found")
                if "attachShadow" not in source:
                    errors.append(f"{where}: page never calls attachShadow")
            elif context != "main":
                errors.append(f"{where}: unknown context {context!r}")

            if not id_in_source(element_id, target_source):
                errors.append(f"{where}: element #{element_id} not found in HTML/JS")

            type_counts[f["type"]] += 1
            category_counts[page["category"]] += 1

        for neg in page.get("hardNegatives", []):
            neg_id = selector_id(neg["selector"])
            if neg_id is None or not id_in_source(neg_id, source):
                errors.append(f"{path}: hard negative {neg['selector']} not found")
            if neg["looksLike"] not in ccpa_refs:
                errors.append(f"{path}: hard negative has unknown type {neg['looksLike']!r}")

    for pattern in ccpa_refs:
        if type_counts[pattern] == 0:
            errors.append(f"pattern {pattern} is not planted anywhere")

    print("Planted findings per pattern:")
    for pattern in ccpa_refs:
        ref = ccpa_refs[pattern]
        print(f"  {pattern:<24} CCPA {ref if ref is not None else '-':<3} x{type_counts[pattern]}")
    print("Planted findings per category:", dict(category_counts))
    hard = sum(len(p.get("hardNegatives", [])) for p in truth["pages"])
    print(f"Total: {sum(type_counts.values())} planted findings, {hard} hard negatives, {len(truth['pages'])} pages")

    if errors:
        print(f"\n{len(errors)} problem(s):")
        for e in errors:
            print("  -", e)
        return 1
    print("\nOK: ground truth matches the pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
