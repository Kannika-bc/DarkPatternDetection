"""DarkLens dashboard (Streamlit).

    streamlit run dashboard/app.py

Pages: Audit a website (agent) · Analyze one page · ML models · About.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # allow `streamlit run dashboard/app.py` from the repo root
    sys.path.insert(0, str(ROOT))

import altair as alt  # noqa: E402  (ships with Streamlit)
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agent.auditor import OLLAMA_MODEL, Auditor, ollama_available  # noqa: E402
from backend.analyzer import analyze  # noqa: E402
from collector.playwright_collector import collect_url  # noqa: E402

st.set_page_config(page_title="DarkLens", page_icon="🔍", layout="wide")

PRODUCT_COLOR, TOTAL_COLOR = "#2a78d6", "#eb6834"  # categorical slots 1 and 2


def findings_table(findings: list) -> pd.DataFrame:
    rows = [{
        **({"Step": f.step} if hasattr(f, "step") else {}),
        "Pattern": f.type.replace("_", " ").title(), "CCPA": f.ccpa_ref or "-", "Status": f.status,
        "Severity": f.severity, "Confidence": round(f.confidence, 2), "Source": f.source, "Evidence": f.text[:120],
    } for f in findings]
    return pd.DataFrame(rows)


def price_chart(price_changes: list) -> alt.Chart:
    """Product price vs bill total per journey step (one axis, markers, legend, hover tooltip)."""
    df = pd.DataFrame([{"Step": p.step, "Amount": p.value, "Series": "Product price" if p.kind == "product" else "Bill total",
                        "Page": p.url.rsplit("/", 1)[-1], "Label": p.label} for p in price_changes])
    color = alt.Color("Series:N", scale=alt.Scale(domain=["Product price", "Bill total"], range=[PRODUCT_COLOR, TOTAL_COLOR]),
                      legend=alt.Legend(orient="top", title=None))
    base = alt.Chart(df).encode(
        x=alt.X("Step:O", title="Journey step", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Amount:Q", title="Amount", scale=alt.Scale(zero=True), axis=alt.Axis(grid=True, gridOpacity=0.3)),
        color=color,
        tooltip=["Series", "Step", "Page", "Label", alt.Tooltip("Amount:Q", format=",.2f")])
    return (base.mark_line(strokeWidth=2) + base.mark_point(size=90, filled=True)).properties(height=280)


# ------------------------------------------------------------------ pages
def page_audit() -> None:
    st.header("Audit a website")
    st.caption("The agent walks the journey (product → cart → checkout), analyses each page, tracks prices "
               "and writes a report grounded in the CCPA guidelines. It never types, logs in or pays.")
    c1, c2, c3 = st.columns([3, 1, 1])
    url = c1.text_input("Start URL", "http://localhost:8090/shop/product.html")
    max_steps = c2.number_input("Max steps", 1, 15, 8)
    headed = c3.checkbox("Show browser", value=False)
    llm_ok = ollama_available()
    use_llm = st.checkbox(f"Use local LLM ({OLLAMA_MODEL} via Ollama)", value=llm_ok, disabled=not llm_ok,
                          help=None if llm_ok else "Ollama not running: the deterministic fallback crawl is used.")
    if not st.button("Run audit", type="primary"):
        return

    auditor = Auditor(url, max_steps=int(max_steps), headless=not headed, use_llm=use_llm)
    result: dict = {}
    worker = threading.Thread(target=lambda: result.setdefault("report", auditor.run()), daemon=True)
    worker.start()
    log_box = st.empty()
    with st.spinner("Auditing..."):
        while worker.is_alive():  # live step log
            log_box.code("\n".join(auditor.tools.log[-25:]) or "starting browser...")
            time.sleep(0.5)
    report = result["report"]
    log_box.code("\n".join(report.log[-25:]))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Trust score", f"{report.trust_score}/100")
    m2.metric("Steps", len(report.steps))
    m3.metric("Findings", len(report.findings))
    m4.metric("LLM", report.model if report.llm_used else "fallback")
    st.caption(f"Stopped because: {report.stop_reason}")

    st.subheader("Summary")
    st.write(report.summary)
    st.subheader("Steps")
    st.dataframe(pd.DataFrame([s.model_dump() for s in report.steps]), hide_index=True, use_container_width=True)
    st.subheader("Findings")
    if report.findings:
        st.dataframe(findings_table(report.findings), hide_index=True, use_container_width=True)
    if report.price_changes:
        st.subheader("Prices across the journey")
        st.altair_chart(price_chart(report.price_changes), use_container_width=True)
        with st.expander("Price table"):
            st.dataframe(pd.DataFrame([p.model_dump() for p in report.price_changes]), hide_index=True)
    if report.ccpa_references:
        st.subheader("CCPA references (retrieved with RAG)")
        for ref in report.ccpa_references:
            origin = "official guidelines" if ref.source.lower().endswith(".pdf") else "DarkLens summary"
            st.markdown(f"**Pattern {ref.pattern}: {ref.name}** _({origin})_: {ref.passage}")
    st.download_button("Download report (JSON)", report.model_dump_json(indent=2), "darklens-audit.json")


def page_analyze() -> None:
    st.header("Analyze one page")
    url = st.text_input("URL", "http://localhost:8090/travel/booking.html")
    settle_ms = st.slider("Wait for delayed popups (ms)", 0, 8000, 3000, 500)
    if not st.button("Collect + analyze", type="primary"):
        return
    with st.spinner("Opening the page in Chromium..."):
        snap = collect_url(url, settle_ms=settle_ms)
        res = analyze(snap)
    c1, c2, c3 = st.columns(3)
    c1.metric("Trust score", f"{res.trust_score}/100")
    c2.metric("Page type", res.page_type)
    c3.metric("Findings", len(res.findings))
    if res.findings:
        st.dataframe(findings_table(res.findings), hide_index=True, use_container_width=True)
        with st.expander("Explanations"):
            for f in res.findings:
                st.markdown(f"**{f.type}**: {f.explanation}")
    else:
        st.success("No dark patterns found.")
    st.subheader("Raw PageSnapshot")
    counts = {k: len(getattr(snap, k)) for k in ("segments", "checkboxes", "buttons", "prices", "popups", "timers")}
    st.write(counts)
    with st.expander("Show JSON"):
        st.json(json.loads(snap.model_dump_json()))


def page_ml() -> None:
    st.header("ML models")
    results = ROOT / "ml" / "results"
    path = results / "comparison.json"
    if not path.exists():
        st.warning("Run `python -m ml.evaluate` first.")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    st.caption(f"Binary task (dark vs not dark), held-out test set n = {data['test_size']} (ec-darkpattern).")
    df = pd.DataFrame(data["models"])[["description", "accuracy", "precision", "recall", "f1", "ms_per_text"]]
    st.dataframe(df.rename(columns={"description": "Model", "ms_per_text": "ms / text"}), hide_index=True,
                 use_container_width=True)
    if data.get("category"):
        st.subheader("Category task (which pattern)")
        st.dataframe(pd.DataFrame(data["category"]), hide_index=True)
    st.subheader("Confusion matrices")
    cols = st.columns(len(data["models"]))
    for col, row in zip(cols, data["models"]):
        img = results / f"confusion_{row['model']}.png"
        if img.exists():
            col.image(str(img), caption=row["description"])
    st.info("Benchmark ≠ real pages. DistilBERT wins on the benchmark, but on real page text (prices, fee rows) it "
            "was >97% sure that ordinary labels were dark patterns. MiniLM + LR is better calibrated, so the live "
            "analyzer uses it, and only to support rules or for very confident (≥0.97) sentence-level hits. "
            "See docs/report/evaluation.md.")


def page_about() -> None:
    st.header("About DarkLens")
    st.markdown("""
DarkLens detects **dark patterns** on any website and maps them to India's **CCPA Guidelines for Prevention
and Regulation of Dark Patterns, 2023**.

**One format, two collectors, one analyzer**
```
 Chrome extension (JS) ─┐   extension/content/collector.js
                        ├──► PageSnapshot JSON ──► Python /analyze ──► Findings + trust score
 Playwright (Python)  ──┘   (injects the same script)    (rules + ML + CCPA mapping)
```
**Analyzer:** page type → 19 rule modules → ML text classifier → merge + confidence → CCPA explanation.

**Agent:** LangGraph `observe → decide (LLM tool call) → act (guarded click) → … → report (RAG + LLM summary)`.

**Privacy:** never reads input values, passwords, hidden fields or cookies. Everything runs on localhost.
""")


PAGES = {"Audit a website": page_audit, "Analyze one page": page_analyze, "ML models": page_ml, "About": page_about}
choice = st.sidebar.radio("DarkLens", list(PAGES))
st.sidebar.caption("Start the test site first:\n`python -m http.server 8090 --directory test-site`")
PAGES[choice]()
