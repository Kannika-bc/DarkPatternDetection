"""DarkLens agentic auditor: a LangGraph state machine driven by a local LLM (Ollama).

Graph
    START -> observe -> decide -> act -> observe -> ... -> report -> END
             (snapshot,   (LLM picks the   (guarded
              analyze,     next click, or   click)
              prices)      'finish')

* observe: collect a PageSnapshot, run the analyzer (with prices seen earlier in the journey),
  record the step, check guardrails (payment page / password field -> stop).
* decide:  the LLM sees the page type, findings so far and the list of clickable elements and calls
  one tool: click_element(text) or finish(). If the LLM is unavailable or answers badly, a simple
  deterministic policy clicks "add to cart / checkout / continue" style buttons instead.
* act:     performs the click through agent/tools.py, where all guardrails live.
* report:  RAG lookup of every pattern found, then the LLM writes a summary grounded ONLY in those
  passages (template summary if no LLM).

Run:  python -m agent.run --url http://localhost:8090/shop/product.html --headed
"""

from __future__ import annotations

import os
import time
from typing import Optional, TypedDict
from urllib.parse import urljoin

import requests
from langgraph.graph import END, START, StateGraph

from agent.models import AuditFinding, AuditReport, AuditStep, CcpaReference, PriceChange
from agent.tools import BrowserTools, Clickable
from backend.ccpa import CCPA_NAMES, info_for
from backend.merger import trust_score
from backend.models import now_iso

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("DARKLENS_LLM", "qwen2.5:7b")
MAX_STEPS = 15
TIME_BUDGET_S = 240  # whole audit

# Fallback policy: journey buttons in order of preference (generic, works on any shop/subscription site).
JOURNEY_WORDS = ["add to cart", "add to bag", "add to basket", "add", "book now", "book", "select", "buy",
                 "view cart", "go to cart", "cart", "proceed to checkout", "checkout", "continue", "proceed",
                 "next", "start free trial", "choose plan", "subscribe", "plans", "account"]
NOT_JOURNEY = ("no ", "no,", "not now", "later", "cancel", "reject", "close", "skip", "back", "wishlist",
               "manage", "rate", "allow", "get the app", "keep my")


class AgentState(TypedDict, total=False):
    start_url: str
    step: int
    max_steps: int
    started: float
    action: str
    reason: str
    next_click: Optional[str]
    done: bool
    stop_reason: str


# ------------------------------------------------------------------ LLM helpers
def ollama_available(model: str = OLLAMA_MODEL) -> bool:
    """True if the Ollama server runs and has the model pulled."""
    try:
        tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=1.5).json()
        names = {m["name"] for m in tags.get("models", [])}
        return model in names or f"{model}:latest" in names
    except Exception:
        return False


def make_llm(model: str = OLLAMA_MODEL):
    from langchain_ollama import ChatOllama

    return ChatOllama(model=model, base_url=OLLAMA_URL, temperature=0, num_ctx=4096)


# The tools the LLM can call in the decide step (descriptions are what the LLM reads).
def _decision_tools():
    from langchain_core.tools import tool

    @tool
    def click_element(text: str, reason: str) -> str:
        """Click the button or link whose visible text is `text` to move to the next step of the
        shopping / booking / subscription journey. `reason` explains why in one sentence."""
        return text

    @tool
    def finish(reason: str) -> str:
        """Stop exploring: the journey is complete (reached checkout / account page) or nothing useful is left."""
        return reason

    return [click_element, finish]


DECIDE_PROMPT = """You are DarkLens, an auditor that explores a website's purchase or subscription journey
to find dark patterns (deceptive design) as defined by India's CCPA 2023 guidelines.
Goal: move forward through the journey (product -> cart -> checkout, or plans -> sign-up -> account/cancel)
so that patterns spanning several pages (drip pricing, basket sneaking, bait and switch, subscription traps)
can be observed. Never try to pay, log in or submit forms (those clicks are blocked anyway).
Prefer buttons that move forward (add to cart, checkout, continue, book). Call `finish` when you reach the
last step before payment or when no forward option remains.

Current page: {url}
Page type: {page_type}
Step {step} of at most {max_steps}
Pages visited: {visited}
Dark patterns found so far: {found}
Clickable elements (choose one by its exact text):
{clickables}
"""


# ------------------------------------------------------------------ the auditor
class Auditor:
    def __init__(self, url: str, max_steps: int = MAX_STEPS, headless: bool = True, use_llm: bool = True,
                 model: str = OLLAMA_MODEL) -> None:
        self.tools = BrowserTools(headless=headless)
        self.report = AuditReport(url=url)
        self.max_steps = min(max_steps, MAX_STEPS)
        self.model = model
        self.llm = None
        if use_llm and ollama_available(model):
            self.llm = make_llm(model)
            self.report.llm_used, self.report.model = True, model
        self.visited: list[str] = []
        self.tried: set[tuple[str, str]] = set()  # (url, clicked text) pairs, to avoid loops
        self._seen_findings: set[tuple[str, str]] = set()
        self.graph = self._build_graph()

    # ---------------- graph
    def _build_graph(self):
        g = StateGraph(AgentState)
        g.add_node("observe", self.observe)
        g.add_node("decide", self.decide)
        g.add_node("act", self.act)
        g.add_node("report", self.write_report)
        g.add_edge(START, "observe")
        g.add_conditional_edges("observe", lambda s: "report" if s.get("done") else "decide")
        g.add_conditional_edges("decide", lambda s: "report" if s.get("done") else "act")
        g.add_edge("act", "observe")
        g.add_edge("report", END)
        return g.compile()

    def run(self) -> AuditReport:
        self.tools.start()
        try:
            self.tools.open_page(self.report.url)
            self.graph.invoke({"start_url": self.report.url, "step": 1, "max_steps": self.max_steps,
                               "started": time.monotonic(), "action": "open", "reason": "start URL"},
                              {"recursion_limit": 4 * MAX_STEPS + 10})
        except Exception as exc:  # never crash without a report
            self.report.stop_reason = f"error: {exc.__class__.__name__}: {exc}"
            self.tools._log(self.report.stop_reason)
            if not self.report.summary:
                self.report.summary = self._template_summary()
        finally:
            self.tools.close()
            self.report.log = self.tools.log
            self.report.finished_at = now_iso()
        return self.report

    # ---------------- nodes
    def observe(self, state: AgentState) -> AgentState:
        t = self.tools
        t.get_snapshot()
        analysis = t.analyze_page()
        step = state["step"]
        url = t.page.url
        self.visited.append(url.split("#")[0])
        for pc in t.track_price(step):
            self.report.price_changes.append(PriceChange(**pc))
        new = 0
        for f in analysis.findings:
            key = (f.type, f.text)
            if key in self._seen_findings:
                continue
            self._seen_findings.add(key)
            self.report.findings.append(AuditFinding(**f.model_dump(), step=step))
            new += 1
        stop = t.stop_reason()
        self.report.steps.append(AuditStep(
            step=step, url=url, action=state.get("action", ""), reason=state.get("reason", ""),
            page_type=analysis.page_type, trust_score=analysis.trust_score, findings=len(analysis.findings),
            note=f"{new} new finding(s)" + (f"; STOP: {stop}" if stop else "")))
        t._log(f"step {step}: {analysis.page_type} page, {len(analysis.findings)} finding(s), trust {analysis.trust_score}")
        if stop:
            return {"done": True, "stop_reason": stop}
        if step >= state["max_steps"]:
            return {"done": True, "stop_reason": f"step limit ({state['max_steps']}) reached"}
        if time.monotonic() - state["started"] > TIME_BUDGET_S:
            return {"done": True, "stop_reason": "time budget exceeded"}
        return {"done": False}

    def decide(self, state: AgentState) -> AgentState:
        url = self.tools.page.url
        # Hide links back to pages we already audited: the journey should only move forward
        # (the LLM otherwise wanders back to the cart and wastes steps).
        options = [c for c in self.tools.list_clickable()
                   if (url, c.text.lower()) not in self.tried
                   and not (c.href and urljoin(url, c.href).split("#")[0] in self.visited)]
        if not options:
            return {"done": True, "stop_reason": "no more forward actions"}
        choice: Optional[str] = None
        reason = ""
        if self.llm is not None:
            choice, reason = self._llm_decide(state, options)
        if choice is None:
            pick = self._fallback_decide(options)
            if pick is None:
                return {"done": True, "stop_reason": "journey complete (no forward button left)"}
            choice, reason = pick.text, "fallback policy: forward journey button"
        if choice == "__finish__":
            return {"done": True, "stop_reason": f"LLM finished: {reason}"}
        self.tried.add((url, choice.lower()))
        return {"next_click": choice, "reason": reason}

    def act(self, state: AgentState) -> AgentState:
        text = state["next_click"] or ""
        result = self.tools.click(text)
        note = "" if result.startswith("http") else f" ({result})"
        return {"step": state["step"] + 1, "action": f"click '{text}'{note}", "reason": state.get("reason", "")}

    # ---------------- decision policies
    def _llm_decide(self, state: AgentState, options: list[Clickable]) -> tuple[Optional[str], str]:
        found = sorted({f.type for f in self.report.findings}) or ["none yet"]
        prompt = DECIDE_PROMPT.format(
            url=self.tools.page.url, page_type=self.tools.analysis.page_type if self.tools.analysis else "?",
            step=state["step"], max_steps=state["max_steps"], visited=", ".join(self.visited[-6:]),
            found=", ".join(found), clickables="\n".join(f"- {c.text}" for c in options[:40]))
        try:
            msg = self.llm.bind_tools(_decision_tools()).invoke(prompt)
            calls = getattr(msg, "tool_calls", None) or []
            if not calls:
                self.tools._log("LLM gave no tool call; using fallback policy")
                return None, ""
            call = calls[0]
            args = call.get("args", {})
            if call["name"] == "finish":
                return "__finish__", str(args.get("reason", ""))
            text = str(args.get("text", "")).strip()
            if any(c.text.lower() == text.lower() for c in options):
                self.tools._log(f"LLM chose {text!r}: {args.get('reason', '')}")
                return text, f"LLM: {args.get('reason', '')}"
            self.tools._log(f"LLM chose unknown element {text!r}; using fallback policy")
        except Exception as exc:
            self.tools._log(f"LLM error ({exc.__class__.__name__}); using fallback policy")
        return None, ""

    def _fallback_decide(self, options: list[Clickable]) -> Optional[Clickable]:
        """Deterministic crawl: first option matching the journey words, skipping visited pages."""
        here = self.tools.page.url
        for word in JOURNEY_WORDS:
            for c in options:
                t = c.text.lower()
                if t.startswith(NOT_JOURNEY) or word not in t:
                    continue
                if c.href and urljoin(here, c.href).split("#")[0] in self.visited:
                    continue
                if not c.href and c.kind == "link":
                    continue
                return c
        return None

    # ---------------- report
    def write_report(self, state: AgentState) -> AgentState:
        r = self.report
        r.stop_reason = r.stop_reason or state.get("stop_reason", "")
        r.trust_score = trust_score(r.findings)
        refs: list[CcpaReference] = []
        try:
            from rag.ccpa_rag import pattern_passage

            for ptype in sorted({f.type for f in r.findings}):
                info = info_for(ptype)
                number = info.ccpa_ref or info.related
                if not number or any(x.pattern == number for x in refs):
                    continue  # generic ML findings have no CCPA pattern; one passage per pattern
                hit = pattern_passage(number, f"{CCPA_NAMES[number]}: {info.name} {info.explanation}")
                if hit:
                    refs.append(CcpaReference(pattern=number, name=CCPA_NAMES[number], passage=hit["text"],
                                              source=hit["source"]))
        except Exception as exc:
            self.tools._log(f"RAG lookup failed: {exc}")
        r.ccpa_references = refs
        r.summary = self._llm_summary() if self.llm is not None else ""
        if not r.summary:
            r.summary = self._template_summary()
        self.tools._log(f"audit finished: {r.stop_reason}")
        return {"done": True}

    def _llm_summary(self) -> str:
        r = self.report
        def ref(f) -> str:
            return f"CCPA {f.ccpa_ref}" if f.ccpa_ref else "not a numbered CCPA pattern"

        # Give the model the exact evidence (incl. the rule's note, e.g. "shown for 1,499, now 1,799")
        # so it never has to compute or guess numbers itself.
        findings = "\n".join(
            f"- step {f.step}: {info_for(f.type).name} ({ref(f)}; {f.status}). Evidence: \"{f.text[:110]}\". "
            f"Detail: {f.explanation.split('. ')[0][:160]}" for f in r.findings[:25])
        prices = "\n".join(f"- step {p.step}: {p.kind} '{p.label}' = {p.value:,.0f}" for p in r.price_changes) or "none"
        passages = "\n".join(f"[CCPA {c.pattern} {c.name}] {c.passage}" for c in r.ccpa_references)
        prompt = (
            "Write a short audit summary (120-200 words) for a consumer, as 2-3 plain paragraphs. "
            "No headings, no markdown, no numbered list.\n"
            "Rules: use ONLY the facts and CCPA passages below. Copy prices exactly as listed; never calculate "
            "or change a number. Cite numbered patterns like (CCPA 8); for findings that are not numbered CCPA "
            "patterns, do not write a CCPA number. 'confirmed' means observed directly; 'unverified' means a "
            "claim that could not be checked: say so. Do not invent anything.\n\n"
            f"Steps taken: {len(r.steps)}; trust score {r.trust_score}/100.\nFindings:\n{findings}\n"
            f"Prices seen:\n{prices}\n\nCCPA passages:\n{passages}\n")
        try:
            return str(self.llm.invoke(prompt).content).strip()
        except Exception as exc:
            self.tools._log(f"LLM summary failed ({exc.__class__.__name__}); using template")
            return ""

    def _template_summary(self) -> str:
        r = self.report
        if not r.findings:
            return f"DarkLens visited {len(r.steps)} page(s) and found no dark patterns. Trust score {r.trust_score}/100."
        by_type: dict[str, list[AuditFinding]] = {}
        for f in r.findings:
            by_type.setdefault(f.type, []).append(f)
        lines = [f"DarkLens followed the journey for {len(r.steps)} step(s) and found {len(r.findings)} "
                 f"dark pattern(s) of {len(by_type)} kind(s). Trust score: {r.trust_score}/100."]
        products = [p for p in r.price_changes if p.kind == "product"]
        totals = [p for p in r.price_changes if p.kind == "total"]
        if products and totals and totals[-1].value > products[0].value:
            lines.append(f"The price grew from {products[0].value:,.0f} ({products[0].label}, step {products[0].step}) "
                         f"to a total of {totals[-1].value:,.0f} at step {totals[-1].step}.")
        for ptype, items in by_type.items():
            info = info_for(ptype)
            ref = f"CCPA {info.ccpa_ref}" if info.ccpa_ref else (f"related to CCPA {info.related}" if info.related else "")
            ref = f" ({ref})" if ref else ""
            lines.append(f"- {info.name}{ref}, step {items[0].step}: \"{items[0].text[:90]}\"")
        return "\n".join(lines)


def run_audit(url: str, max_steps: int = MAX_STEPS, headless: bool = True, use_llm: bool = True) -> AuditReport:
    """Convenience wrapper used by the CLI, the API (/audit) and the dashboard."""
    return Auditor(url, max_steps=max_steps, headless=headless, use_llm=use_llm).run()
