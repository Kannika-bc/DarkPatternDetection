"""The agent's tools: a guarded Playwright browser + the DarkLens analyzer + price memory + RAG.

Tools: open_page(url), get_snapshot(), analyze_page(), list_clickable(),
click(text), track_price(), ccpa_lookup(query).

Guardrails live HERE (not in the LLM prompt), so no LLM answer can bypass them:
* only http(s) URLs; never type into any input; per-action timeouts;
* refuse to click anything that pays / places an order / signs in;
* report a page as a "stop page" if it asks for payment details or a password.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from backend.analyzer import analyze
from backend.models import AnalyzeResponse, PageSnapshot, PreviousPrice
from backend.rules.drip_pricing import page_total
from collector.playwright_collector import check_timer_resets, collect_snapshot, settle

NAV_TIMEOUT_MS = 15_000
CLICK_TIMEOUT_MS = 4_000

# Never click these: they spend money, submit personal data or log in.
FORBIDDEN_CLICK = re.compile(
    r"\b(pay|payment|place (your )?order|confirm (and pay|order|booking|purchase)|purchase|buy now and pay|"
    r"submit|sign ?in|log ?in|log ?out|sign ?out|delete|remove|unsubscribe|create account|register)\b",
    re.IGNORECASE)
# Links that only change the page section or open something external are not journey steps.
SKIP_HREF = re.compile(r"^(#|javascript:|mailto:|tel:)", re.IGNORECASE)

PAYMENT_FIELD_JS = """() => !!document.querySelector(
  'input[type=password], input[autocomplete^="cc-"], input[name*="card" i], input[name*="cvv" i], input[name*="upi" i], iframe[src*="pay" i]')"""


@dataclass
class Clickable:
    index: int
    element_id: str
    text: str
    kind: str
    href: Optional[str] = None


@dataclass
class BrowserTools:
    headless: bool = True
    settle_ms: int = 3500
    log: list[str] = field(default_factory=list)
    price_history: list[PreviousPrice] = field(default_factory=list)
    _pw: Optional[Playwright] = None
    _browser: Optional[Browser] = None
    page: Optional[Page] = None
    snapshot: Optional[PageSnapshot] = None
    analysis: Optional[AnalyzeResponse] = None
    clickables: list[Clickable] = field(default_factory=list)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless, slow_mo=250 if not self.headless else 0)
        self.page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        self.page.set_default_timeout(CLICK_TIMEOUT_MS)
        self.page.set_default_navigation_timeout(NAV_TIMEOUT_MS)

    def close(self) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def _log(self, msg: str) -> None:
        self.log.append(msg)
        print(f"[agent] {msg}")

    # ------------------------------------------------------------------ tools
    def open_page(self, url: str) -> str:
        """Navigate to a URL (http/https only) and wait for it to settle."""
        if not url.startswith(("http://", "https://")):
            self._log(f"BLOCKED open_page({url!r}): only http(s) URLs are allowed")
            return "blocked: only http(s) URLs"
        self.page.goto(url, wait_until="domcontentloaded")
        settle(self.page, self.settle_ms)
        self._log(f"opened {self.page.url}")
        return self.page.url

    def get_snapshot(self, check_timers: bool = True) -> PageSnapshot:
        """Collect a PageSnapshot of the current page with the shared collector.

        If the page shows countdowns, reload it once to see whether they restart (fake deadline).
        """
        snap = collect_snapshot(self.page)
        if check_timers and snap.timers:
            check_timer_resets(self.page, snap)  # reloads the page
            resets = [t.reset_on_reload for t in snap.timers]
            settle(self.page, self.settle_ms)
            snap = collect_snapshot(self.page)  # fresh ids for the reloaded page
            for i, t in enumerate(snap.timers):
                t.reset_on_reload = resets[i] if i < len(resets) else None
            self._log(f"timer reload check: reset_on_reload={resets}")
        self.snapshot = snap
        return snap

    def analyze_page(self) -> AnalyzeResponse:
        """Run the DarkLens analyzer, passing the prices seen earlier in this journey."""
        snap = self.snapshot or self.get_snapshot()
        snap.previous_prices = list(self.price_history)
        self.analysis = analyze(snap)
        return self.analysis

    def track_price(self, step: int) -> list[dict]:
        """Remember the product price (first time seen) and the bill total of this page."""
        out: list[dict] = []
        if self.analysis and self.analysis.price_observation:
            obs = self.analysis.price_observation
            if not any(p.label == obs.label for p in self.price_history):
                self.price_history.append(PreviousPrice(**obs.model_dump()))
            out.append({"step": step, "url": self.page.url, "label": obs.label, "value": obs.value,
                        "currency": obs.currency, "kind": "product"})
        if self.snapshot:
            total = page_total(self.snapshot)
            if total:
                currency = next((p.currency for p in self.snapshot.prices if p.value == total), None)
                out.append({"step": step, "url": self.page.url, "label": "Total", "value": total,
                            "currency": currency, "kind": "total"})
        return out

    def list_clickable(self) -> list[Clickable]:
        """Visible buttons/links the agent may click (forbidden and same-page links removed)."""
        snap = self.snapshot or self.get_snapshot()
        hrefs = self.page.evaluate(
            "ids => ids.map(id => { const e = window.DarkLensCollector.elementFor(id); return e && e.getAttribute('href'); })",
            [b.id for b in snap.buttons])
        items: list[Clickable] = []
        seen: set[str] = set()
        for b, href in zip(snap.buttons, hrefs):
            text = b.text.strip()
            if not text or text.lower() in seen or len(text) > 60:
                continue
            if FORBIDDEN_CLICK.search(text) or (href and SKIP_HREF.match(href)):
                continue
            seen.add(text.lower())
            items.append(Clickable(len(items), b.id, text, b.kind, href))
        self.clickables = items
        return items

    def click(self, text: str) -> str:
        """Click the clickable whose text matches ``text`` (guarded). Returns the new URL or an error."""
        if FORBIDDEN_CLICK.search(text):
            self._log(f"BLOCKED click({text!r}): looks like payment / login / submit")
            return "blocked"
        target = next((c for c in self.clickables if c.text.lower() == text.lower()), None) or \
            next((c for c in self.clickables if text.lower() in c.text.lower()), None)
        if not target:
            return f"error: no clickable element with text {text!r}"
        loc = self.page.locator(f'[data-darklens-id="{target.element_id}"]').first
        before = self.page.url
        try:
            loc.click(timeout=CLICK_TIMEOUT_MS)
        except Exception:
            # Usually an overlay (popup) is in the way: dispatch the click on the element directly.
            self._log(f"normal click on {target.text!r} was blocked (overlay?), dispatching click event")
            try:
                loc.dispatch_event("click")
            except Exception as exc:
                return f"error: {exc.__class__.__name__}"
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
        except Exception:
            pass
        settle(self.page, self.settle_ms)
        self.snapshot = None
        self._log(f"clicked {target.text!r}: {before} -> {self.page.url}")
        return self.page.url

    def stop_reason(self) -> Optional[str]:
        """Return why the agent must stop on this page (payment/password fields or payment URL)."""
        url = self.page.url.lower()
        if re.search(r"/(pay|payment|payments)(/|\.|$|\?)", url):
            return "reached a payment page"
        if self.page.evaluate(PAYMENT_FIELD_JS):
            return "page asks for a password or payment details"
        return None
