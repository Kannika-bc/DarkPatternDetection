"""DarkLens FastAPI backend (localhost only).

    uvicorn backend.main:app --port 8000

Endpoints
* GET  /health   -> status + which ML model is loaded
* POST /analyze  -> PageSnapshot in, findings + page_type + trust_score out
* POST /audit    -> run the agentic auditor on a URL (see agent/)
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.analyzer import analyze, get_classifier
from backend.models import AnalyzeResponse, PageSnapshot

app = FastAPI(title="DarkLens", version="1.0", description="Dark pattern detection API (CCPA 2023)")

# CORS: the Chrome extension (and the test site) call us from other origins. We only ever listen
# on localhost, so allowing any origin does not expose the API to the internet.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/health")
def health() -> dict:
    clf = get_classifier()
    return {"status": "ok", "ml_model": clf.name if clf else None}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze_endpoint(snapshot: PageSnapshot) -> AnalyzeResponse:
    return analyze(snapshot)


class AuditRequest(BaseModel):
    url: str
    max_steps: int = 15
    headless: bool = True
    use_llm: bool = True


@app.post("/audit")
def audit_endpoint(req: AuditRequest) -> dict:
    if not req.url.startswith(("http://", "https://")):
        raise HTTPException(400, "Only http(s) URLs are allowed")
    from agent.auditor import run_audit  # imported lazily: Playwright + LangGraph are heavy

    report = run_audit(req.url, max_steps=min(req.max_steps, 15), headless=req.headless, use_llm=req.use_llm)
    return report.model_dump()
