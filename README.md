# DarkPatternDetection (DarkLens)

Detects **dark patterns** (deceptive design such as fake countdowns, pre-ticked boxes, hidden fees and
shaming "No thanks" buttons) on any website and maps each one to India's **CCPA Guidelines for
Prevention and Regulation of Dark Patterns, 2023**.

## Features

- **Chrome extension**: highlights dark patterns on the page, shows a trust score, and can undo
  pre-ticked boxes and pre-selected tips.
- **Python analyzer (FastAPI)**: rule-based detectors plus an ML text classifier.
- **ML models**: TF-IDF + Logistic Regression, MiniLM embeddings + Logistic Regression, fine-tuned DistilBERT.
- **AI agent (LangGraph + Ollama)**: walks a site from product to cart to checkout, tracks prices
  across pages and writes an audit report using the CCPA guidelines (RAG with ChromaDB).
- **Dashboard (Streamlit)**: run audits, analyze single pages, compare ML models.
- **Test site**: fake shops with planted dark patterns and a clean shop for false-positive checks.
- **Privacy**: never reads form values, passwords or cookies; everything runs on localhost.

## Project structure

```
backend/     FastAPI app, rules, ML integration, CCPA mapping
collector/   Playwright page collector
extension/   Chrome extension (plain JavaScript)
ml/          data preparation, training, evaluation, predictor
rag/         CCPA knowledge base (ChromaDB)
agent/       LangGraph auditing agent
dashboard/   Streamlit app
shared/      PageSnapshot JSON schema
test-site/   test websites with planted patterns
scripts/     evaluation and validation scripts
tests/       pytest tests
```

## Setup (Windows PowerShell)

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.venv\Scripts\Activate.ps1
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
playwright install chromium
```

Train the ML models (data is downloaded automatically):

```powershell
python -m ml.prepare_data
python -m ml.train_baseline
python -m ml.train_embeddings
python -m ml.train_distilbert     # optional, slower
python -m ml.evaluate
```

Optional, for the AI agent: install [Ollama](https://ollama.com/download), then run `ollama pull qwen2.5:7b`.
Optional, for official CCPA text in reports: put the guidelines PDF in `rag/data/`, then run
`python -m rag.ccpa_rag --rebuild`.

## Run

Use three terminals (activate the venv in each):

```powershell
python -m http.server 8090 --directory test-site   # test site  -> http://localhost:8090
uvicorn backend.main:app --port 8000               # API        -> http://localhost:8000/docs
streamlit run dashboard/app.py                     # dashboard  -> http://localhost:8501
```

**Chrome extension:** open `chrome://extensions`, enable *Developer mode*, click *Load unpacked*
and select the `extension` folder. Then open http://localhost:8090/shop/product.html.

**Agent from the command line:**

```powershell
python -m agent.run --url http://localhost:8090/shop/product.html --headed
```

**Tests and evaluation:**

```powershell
pytest -q
python -m scripts.evaluate_test_site
```

## Datasets

- Mathur et al. (2019), *Dark Patterns at Scale*: https://github.com/aruneshmathur/dark-patterns
- Yada et al. (2022), *ec-darkpattern*: https://github.com/yamanalab/ec-darkpattern

## License

MIT
