# DarkLens

Detects **dark patterns** (deceptive UI design) on any website, explains them, helps users undo
them, and maps each finding to India's CCPA *Guidelines for Prevention and Regulation of Dark
Patterns, 2023*. Python core (rules + ML + LangGraph agent + RAG), thin plain-JS Chrome extension.

See `docs/PLAN.md` for the design. Full documentation follows in milestone M6.

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.venv\Scripts\Activate.ps1
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
playwright install chromium

python -m http.server 8090 --directory test-site   # terminal 1: test site
uvicorn backend.main:app --port 8000               # terminal 2: API
pytest -q
```

License: MIT.
