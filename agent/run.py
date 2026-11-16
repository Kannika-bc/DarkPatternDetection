"""CLI for the agentic auditor.

    python -m agent.run --url http://localhost:8090/shop/product.html --headed
    python -m agent.run --url http://localhost:8090/food/menu.html --no-llm --out reports/food.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agent.auditor import OLLAMA_MODEL, ollama_available, run_audit


def main() -> None:
    ap = argparse.ArgumentParser(description="DarkLens agentic auditor")
    ap.add_argument("--url", required=True)
    ap.add_argument("--max-steps", type=int, default=15)
    ap.add_argument("--headed", action="store_true", help="show the browser so you can watch")
    ap.add_argument("--no-llm", action="store_true", help="use only the deterministic crawl")
    ap.add_argument("--out", help="save the AuditReport JSON here")
    a = ap.parse_args()

    if not a.no_llm and not ollama_available():
        print(f"[agent] Ollama model '{OLLAMA_MODEL}' not reachable -> deterministic fallback crawl.")
    report = run_audit(a.url, max_steps=a.max_steps, headless=not a.headed, use_llm=not a.no_llm)

    print("\n================ DarkLens audit report ================")
    print(f"URL: {report.url}\nLLM: {report.model if report.llm_used else 'not used (fallback crawl)'}")
    print(f"Stopped because: {report.stop_reason}\nTrust score: {report.trust_score}/100\n")
    print("Steps:")
    for s in report.steps:
        print(f"  {s.step}. {s.action:40} -> {s.url}  [{s.page_type}, {s.findings} findings] {s.note}")
    print("\nPrices:")
    for p in report.price_changes:
        print(f"  step {p.step}: {p.kind:7} {p.label[:40]:40} {p.value:>10,.2f} {p.currency or ''}")
    print("\nFindings:")
    for f in report.findings:
        print(f"  step {f.step}: {f.type:22} CCPA {str(f.ccpa_ref or '-'):3} {f.status:10} {f.text[:70]}")
    print("\nCCPA references (RAG):")
    for c in report.ccpa_references:
        print(f"  [{c.pattern}] {c.passage[:110]}")
    print(f"\nSummary:\n{report.summary}")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(f"\nSaved {a.out}")


if __name__ == "__main__":
    main()
