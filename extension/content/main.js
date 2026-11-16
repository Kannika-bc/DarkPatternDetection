// DarkLens content script: the "thin client" part that runs inside every web page.
//
// 1. Collect a PageSnapshot (collector.js) and add previously seen prices for this site.
// 2. Ask the background worker to send it to the Python backend (POST /analyze).
// 3. Draw a red dashed outline around each finding, with a tooltip on hover.
// 4. Re-scan when the page changes (new content, popups, single-page-app URL changes).
// 5. Answer the popup's commands: get results, show a finding, fix one / fix all, download snapshot.
//
// All detection logic is in Python. This file only collects, sends and draws.

(function () {
  "use strict";
  if (window.__darklensMain) return; // already running in this page
  window.__darklensMain = true;

  let lastResult = null; // latest answer from the backend
  let lastSnapshot = null; // latest snapshot we sent (for the debug download)
  let lastSignature = ""; // fingerprint of the last snapshot, to avoid re-sending identical pages
  let scanTimer = null;
  const flagged = new Map(); // element -> its original inline outline (to undo highlights)
  const popupSeen = new Map(); // popup element -> was it visible at the last scan? (nagging counter)

  // ------------------------------------------------------------------ previous prices

  /** Storage key for prices seen on this website (one list per site/origin). */
  function priceKey() {
    return "darklens-prices:" + location.origin;
  }

  /** Read the first-seen prices for this site from chrome.storage. */
  async function loadPreviousPrices() {
    try {
      const data = await chrome.storage.local.get(priceKey());
      return data[priceKey()] || [];
    } catch (e) {
      return [];
    }
  }

  /** Remember the main price of a product page, but only the FIRST time we see that product. */
  async function rememberPrice(observation) {
    if (!observation) return;
    const list = await loadPreviousPrices();
    if (list.some((p) => p.label === observation.label)) return; // keep the first-seen price
    list.push(observation);
    await chrome.storage.local.set({ [priceKey()]: list.slice(-20) });
  }

  // ------------------------------------------------------------------ nagging counter

  /** Count how often each popup has (re)appeared, so the backend can confirm nagging. */
  function updatePopupCounts(snapshot) {
    const visibleNow = new Set();
    snapshot.popups.forEach((p) => {
      const el = window.DarkLensCollector.elementFor(p.id);
      if (!el) return;
      visibleNow.add(el);
      let shown = parseInt(el.getAttribute("data-darklens-shown") || "1", 10);
      if (popupSeen.get(el) === false) {
        shown += 1; // it was hidden at the last scan and is back again
        el.setAttribute("data-darklens-shown", String(shown));
      }
      p.times_shown = shown;
    });
    popupSeen.forEach((_, el) => popupSeen.set(el, visibleNow.has(el)));
    visibleNow.forEach((el) => popupSeen.set(el, true));
  }

  /** Fingerprint of a snapshot ignoring digits (a ticking timer should not trigger a re-analysis). */
  function signature(snapshot) {
    const parts = [
      snapshot.url,
      snapshot.segments.map((s) => s.text).join("|"),
      snapshot.checkboxes.map((c) => c.id + c.checked).join(","),
      snapshot.popups.map((p) => p.id + ":" + p.times_shown).join(","),
    ];
    return parts.join("#").replace(/\d/g, "");
  }

  // ------------------------------------------------------------------ scanning

  /** Collect, send to the backend and draw the findings. */
  async function scan(force) {
    const snapshot = window.DarkLensCollector.collect("extension");
    updatePopupCounts(snapshot);
    snapshot.previous_prices = await loadPreviousPrices();
    const sig = signature(snapshot);
    if (!force && sig === lastSignature) return; // nothing important changed
    lastSignature = sig;
    lastSnapshot = snapshot;

    const result = await chrome.runtime.sendMessage({ type: "analyze", snapshot });
    lastResult = result;
    if (!result || result.error) {
      clearHighlights();
      return;
    }
    await rememberPrice(result.price_observation);
    drawHighlights(result.findings);
  }

  /** Schedule a scan soon; many DOM changes in a row cause only one scan. */
  function scheduleScan(delayMs) {
    if (scanTimer) return; // one is already pending
    scanTimer = setTimeout(() => {
      scanTimer = null;
      scan(false).catch((e) => console.warn("[DarkLens]", e));
    }, delayMs);
  }

  // ------------------------------------------------------------------ highlights + tooltip

  const tooltip = document.createElement("div");
  tooltip.id = "darklens-tooltip";

  /** Remove all outlines we drew. */
  function clearHighlights() {
    flagged.forEach((oldOutline, el) => {
      el.style.outline = oldOutline;
      el.removeAttribute("data-darklens-finding");
    });
    flagged.clear();
  }

  /** Outline every element that has a finding. Inline styles also work inside shadow DOM/iframes. */
  function drawHighlights(findings) {
    clearHighlights();
    findings.forEach((f, index) => {
      const el = f.element_id && window.DarkLensCollector.elementFor(f.element_id);
      if (!el || flagged.has(el)) return;
      flagged.set(el, el.style.outline);
      el.style.outline = "2px dashed #dc2626";
      el.style.outlineOffset = "2px";
      el.setAttribute("data-darklens-finding", String(index));
      el.addEventListener("mouseenter", showTooltip);
      el.addEventListener("mouseleave", hideTooltip);
    });
  }

  /** Small HTML escaper so page text can never inject markup into our tooltip. */
  function esc(text) {
    const d = document.createElement("div");
    d.textContent = text || "";
    return d.innerHTML;
  }

  /** Show type, CCPA reference and explanation next to the hovered element. */
  function showTooltip(event) {
    const index = event.currentTarget.getAttribute("data-darklens-finding");
    const f = lastResult && lastResult.findings && lastResult.findings[index];
    if (!f) return;
    if (!tooltip.isConnected) document.documentElement.appendChild(tooltip);
    const ccpa = f.ccpa_ref ? "CCPA pattern " + f.ccpa_ref : "Related to CCPA guidelines";
    tooltip.innerHTML =
      "<b>" + esc(f.type.replace(/_/g, " ")) + "</b>" +
      '<div class="dl-meta">' + esc(ccpa) + " · " + esc(f.status) + " · " + Math.round(f.confidence * 100) + "% sure</div>" +
      esc(f.explanation);
    const r = event.currentTarget.getBoundingClientRect();
    tooltip.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 360)) + "px";
    tooltip.style.top = (r.bottom + 8 < window.innerHeight - 120 ? r.bottom + 8 : Math.max(8, r.top - 130)) + "px";
    tooltip.style.display = "block";
  }

  function hideTooltip() {
    tooltip.style.display = "none";
  }

  // ------------------------------------------------------------------ popup commands

  /** Scroll to a finding's element and make it flash. */
  function showFinding(f) {
    const el = f.element_id && window.DarkLensCollector.elementFor(f.element_id);
    if (!el) return false;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("darklens-flash");
    void el.offsetWidth; // restart the animation
    el.classList.add("darklens-flash");
    return true;
  }

  /**
   * Undo a fixable dark pattern:
   * - a pre-ticked checkbox -> untick it
   * - a pre-selected tip/donation radio -> select the "no tip" / first option of the same group
   * We use click() so the website's own code notices the change (it fires input + change events).
   */
  function fixFinding(f) {
    if (!f.fixable) return false;
    const el = f.element_id && window.DarkLensCollector.elementFor(f.element_id);
    if (!el || el.tagName !== "INPUT") return false;
    if (el.type === "checkbox") {
      if (el.checked) el.click();
      return !el.checked;
    }
    if (el.type === "radio" && el.name) {
      const root = el.form || el.getRootNode();
      const options = Array.from(root.querySelectorAll('input[type="radio"]')).filter((r) => r.name === el.name);
      const labelOf = (r) => ((r.labels && r.labels[0] && r.labels[0].innerText) || "").trim();
      const noOption = options.find((r) => /^(no\b|none|skip|0\b)/i.test(labelOf(r))) || options[0];
      if (noOption && noOption !== el) noOption.click();
      return !el.checked;
    }
    return false;
  }

  /** Save the last snapshot as a JSON file (to validate it against the schema in Python). */
  function downloadSnapshot() {
    const snapshot = lastSnapshot || window.DarkLensCollector.collect("extension");
    const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "darklens-snapshot.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // Messages from the popup: { cmd: "get" | "show" | "fix" | "fixAll" | "rescan" | "download", index }
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    const findings = (lastResult && lastResult.findings) || [];
    if (msg.cmd === "get") {
      sendResponse(lastResult);
    } else if (msg.cmd === "show") {
      sendResponse({ ok: showFinding(findings[msg.index]) });
    } else if (msg.cmd === "fix") {
      sendResponse({ ok: fixFinding(findings[msg.index]) });
    } else if (msg.cmd === "fixAll") {
      const fixed = findings.filter((f) => f.fixable && fixFinding(f)).length;
      sendResponse({ fixed });
    } else if (msg.cmd === "rescan") {
      scan(true).then(() => sendResponse(lastResult));
      return true; // async answer
    } else if (msg.cmd === "download") {
      downloadSnapshot();
      sendResponse({ ok: true });
    }
    return false;
  });

  // ------------------------------------------------------------------ watch the page

  // Re-scan when nodes are added/removed or a class/style changes (popups appearing).
  // Our own highlights only change inline styles of flagged elements; the signature check above
  // stops those from causing endless re-analysis.
  const observer = new MutationObserver((mutations) => {
    const relevant = mutations.some((m) => m.target !== tooltip && !tooltip.contains(m.target));
    if (relevant) scheduleScan(1500);
  });
  observer.observe(document.documentElement, {
    childList: true, subtree: true, attributes: true, attributeFilter: ["class", "hidden", "open"],
  });

  // Single-page apps change the URL without reloading: check it every second.
  let lastUrl = location.href;
  setInterval(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      scheduleScan(800);
    }
  }, 1000);

  // First scan shortly after the page is ready.
  scheduleScan(800);
})();
