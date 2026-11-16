# DarkLens

**Detects, explains and helps undo dark patterns (deceptive UI design) on any website, mapped to
India's CCPA *Guidelines for Prevention and Regulation of Dark Patterns, 2023*.**

Python core (rule engine + ML text classifiers + LangGraph agent + CCPA RAG), a thin plain-JavaScript
Chrome extension, and a Streamlit dashboard. 100% open source, runs entirely on your own laptop.

## The problem

Countdown timers that restart on reload, pre-ticked insurance, a ₹20 tip selected for you, fees that
appear only at checkout, a giant "Accept" next to a tiny grey "reject"... Since November 2023 the CCPA
prohibits 13 such patterns, but users rarely recognise them and nobody can audit millions of pages by
hand. DarkLens finds them automatically, explains each one in plain language with its CCPA reference,
and can undo some of them with one click.

## Features

* **19 pattern detectors**: all 12 in-scope CCPA patterns (False Urgency, Basket Sneaking, Confirm
  Shaming, Forced Action, Subscription Trap, Interface Interference, Bait and Switch, Drip Pricing,
  Disguised Ads, Nagging, Trick Questions, SaaS Billing) plus pre-checked opt-ins, pre-selected tips,
  fake scarcity, fake social proof, fake discounts, cookie walls and auto-renew.
* **Confirmed vs unverified**: observable facts (a box *is* ticked, a timer *did* reset, a price
  *did* change between pages) are *confirmed*; claims we cannot check ("only 2 left") are *unverified*.
* **Chrome extension**: red dashed highlights with tooltips, trust score, "Show", "Fix", "Fix all".
* **Agentic auditor**: walks product → cart → checkout, tracks prices across pages, stops before payment.
* **CCPA RAG**: every report cites the relevant guideline passages retrieved from ChromaDB.
* **ML comparison**: TF-IDF+LR vs MiniLM embeddings+LR vs fine-tuned DistilBERT.
* **Privacy by design**: never reads form values, passwords, hidden fields or cookies; localhost only.

## Architecture: one format, two collectors, one analyzer

```
 Chrome extension (JS) ─┐  extension/content/collector.js
                        ├──► PageSnapshot JSON ──► POST /analyze (FastAPI, Python)
 Playwright (Python)  ──┘  injects the SAME script        │
                                                          ├─ page_type.py   product / cart / checkout / ...
                                                          ├─ rules/         one module per pattern (19)
                                                          ├─ ML classifier  MiniLM + LR on text segments
                                                          ├─ merger.py      dedupe, confidence, status
                                                          └─ ccpa.py        CCPA ref, severity, explanation
                                                                 ▼
                                                     Findings + trust score (0-100)

 LangGraph agent:  observe ─► decide (LLM tool call) ─► act (guarded click) ─► observe ... ─► report
                   tools: open_page, get_snapshot, analyze_page, list_clickable, click, track_price, ccpa_lookup
```

**PageSnapshot** (schema: `shared/page_snapshot.schema.json`, mirrored by `backend/models.py`):
visible text segments (with fine print), checkboxes/radios (state + label), buttons (size, font,
colours, group), prices (value, currency, struck-through, row context), popups, timers, and
`previous_prices` (first price seen on this site, for cross-page patterns). Both collectors run the
same `collector.js`, so their output is identical by construction. Details: `docs/PLAN.md` §5 and
`docs/report/extension-explained.md`.

## Tech stack

Python 3.12 · FastAPI · Pydantic · Playwright · scikit-learn · sentence-transformers · Hugging Face
Transformers + PyTorch · LangGraph + LangChain-Ollama · ChromaDB · Streamlit · pytest ·
Chrome Manifest V3 (plain JS, no build step). All MIT / Apache-2.0 / BSD.

## Setup (Windows PowerShell)

```powershell
cd darklens
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.venv\Scripts\Activate.ps1
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU build (~200 MB)
pip install -r requirements.txt
playwright install chromium
```

*Optional, NVIDIA GPU:* replace the torch line with
`pip install torch --index-url https://download.pytorch.org/whl/cu124` to fine-tune DistilBERT in ~2 min.

**Local LLM (optional, for the agent):** install Ollama from <https://ollama.com/download> (Windows
installer), then `ollama pull qwen2.5:7b`. It fits a 16 GB laptop with an 8 GB GPU and has reliable
tool calling. On a weaker machine use `ollama pull qwen2.5:3b` and set `$env:DARKLENS_LLM="qwen2.5:3b"`.
Without Ollama the agent uses its deterministic fallback crawl, and everything else works.

## How to run each part

| What | Command |
|---|---|
| Test site | `python -m http.server 8090 --directory test-site` → <http://localhost:8090> |
| Backend API | `uvicorn backend.main:app --port 8000` → <http://localhost:8000/docs> |
| Collect one page | `python -m collector.run --url http://localhost:8090/shop/product.html --out snapshot.json` |
| ML pipeline | `python -m ml.prepare_data` · `python -m ml.train_baseline` · `python -m ml.train_embeddings` · `python -m ml.train_distilbert` (or Colab notebook) · `python -m ml.evaluate` |
| RAG index | `python -m rag.ccpa_rag --rebuild "fees added at checkout"` |
| Agent | `python -m agent.run --url http://localhost:8090/shop/product.html --headed` |
| Test-site evaluation | `python -m scripts.evaluate_test_site` → `docs/report/evaluation.md` |
| Dashboard | `streamlit run dashboard/app.py` → <http://localhost:8501> |
| Tests | `pytest -q` (71 tests) |

**Chrome extension:** `chrome://extensions` → enable *Developer mode* → *Load unpacked* → select the
`extension/` folder. Start the backend and the test site, open <http://localhost:8090/shop/product.html>
and click the DarkLens icon. Walk product → cart → checkout to see the cross-page findings appear
(bait and switch, confirmed drip pricing). Use **Fix all** on `food/cart.html` to remove the tip and
donation. "Debug: snapshot" downloads the PageSnapshot; check it with
`python -m scripts.validate_snapshot $HOME\Downloads\darklens-snapshot.json`.

## Results

**ML (ec-darkpattern test set, n = 339)**: `ml/results/comparison.md`

| Model | Accuracy | Precision | Recall | F1 | ms/text (CPU) |
|---|---|---|---|---|---|
| DistilBERT fine-tuned | 0.971 | 0.975 | 0.963 | **0.969** | 17.2 |
| TF-IDF + Logistic Regression | 0.950 | 0.993 | 0.902 | 0.946 | 0.02 |
| MiniLM embeddings + LR | 0.932 | 0.961 | 0.896 | 0.927 | 4.5 |

**Key finding: the benchmark winner is not the best model for real pages.** On test-site text,
DistilBERT was >97% confident that plain labels like "Item total" or "Rs 25.00" are dark patterns
(68 false alarms). MiniLM+LR is much better calibrated (2 false alarms at the same threshold), so the
live analyzer uses MiniLM (`DARKLENS_MODEL` to override), and only to support rules or for very
confident sentence-level hits.

**System (test site, 42 planted patterns, 17 hard negatives)**: `docs/report/evaluation.md`

* Recall **41/42 (97.6%)**, precision **95.3%**, F1 **0.965**
* **0 false positives on the clean site** (0 of 17 look-alike "hard negatives" flagged)
* Page-type detector 16/16. Miss: the news "notifications" nag, which only appears after the user
  dismisses the cookie wall.

**Agent example** (`docs/report/agent-report-shop.json`): product → cart → checkout in 3 steps,
stopped before "Continue to payment"; found 11 patterns incl. *confirmed* bait and switch
(₹1,499 → ₹1,799), *confirmed* drip pricing (handling + transaction fees, total ₹2,246) and a
*confirmed* fake countdown (restarted on reload). Trust score 21/100.

## Limitations

English text only; claims like "only 2 left" cannot be proven false from outside (→ unverified);
behaviour patterns need time or interaction; closed shadow roots and cross-origin iframes are
invisible; the public datasets are from 2019–2022 global e-commerce sites, not Indian ones; the test
site is small and written by the same team as the rules, so real-world accuracy will be lower;
the LLM path needs Ollama and was developed against the fallback crawl.

## Privacy & ethics

No input values, passwords, hidden fields, cookies or history are ever read (tested in
`tests/test_e2e.py`). The backend and dashboard listen on localhost only; the LLM runs locally. The
agent never types, logs in or pays. Findings are signals for consumers, not legal verdicts.

## Future work

In-browser inference (ONNX / Transformers.js) · Hindi/Hinglish (MuRIL, IndicBERT) · vision LLM on
screenshots · a labelled dataset of Indian sites · large-scale real-site study · PDF audit reports.

## License

MIT (see `LICENSE`). Datasets are downloaded at runtime and not redistributed: please cite
Mathur et al. (2019) and Yada et al. (2022).
