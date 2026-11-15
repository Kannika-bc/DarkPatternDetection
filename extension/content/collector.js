// DarkLens collector: builds a PageSnapshot (see shared/page_snapshot.schema.json).
//
// This ONE file is used by BOTH collectors:
//   * the Chrome extension loads it as a content script, and
//   * the Python Playwright collector injects it into the page (collector/playwright_collector.py).
// So both always produce exactly the same format.
//
// It only READS what is visible on the page. It never reads what a user typed into a form
// (input values), password fields, hidden inputs, cookies or localStorage.
//
// Usage:  const snapshot = window.DarkLensCollector.collect("extension");
// Plain JavaScript, no libraries, no build step.

(function () {
  "use strict";

  // Run only once per page (content scripts and Playwright may inject it twice).
  if (window.DarkLensCollector) return;

  const MAX_SEGMENTS = 2000; // cap from the design
  const MAX_TEXT = 300; // max characters per text segment
  const MAX_BUTTONS = 400;
  const FINE_PRINT_PX = 12; // text smaller than this counts as "fine print"

  // Elements whose text we never collect.
  const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "SVG", "INPUT",
    "TEXTAREA", "SELECT", "OPTION", "IFRAME", "CANVAS", "HEAD", "META", "LINK"]);

  // Currency symbols / codes we understand (the Python price parser re-checks these).
  const PRICE_RE = /(?<![A-Za-z])(₹|Rs\.?|INR|US\$|\$|€|£|EUR|GBP|USD)\s?\d[\d,]*(\.\d+)?/gi;
  // Countdown formats: 12:34, 01:02:03, "2h 15m", "5 mins left".
  const TIMER_RE = /\b(\d{1,2}:\d{2}(:\d{2})?)\b(?!\s*(am|pm|AM|PM|→|-))|\b(\d+\s*h(ours?|rs?)?\s*\d+\s*m(in(ute)?s?)?)\b|\b(\d+\s*(min(ute)?s?|hours?|hrs?|seconds?|secs?)\s+(left|remaining))\b/;
  // Words near a clock-like number that mean it is a countdown and not a clock time.
  const TIMER_CONTEXT_RE = /(ends? in|ending|left|remaining|expires?|hurry|locked|countdown|deal|offer|sale ends|closing|held for)/i;

  // ------------------------------------------------------------------ small helpers

  /** Give an element a stable temporary id (data-darklens-id="el-N") and remember it. */
  let counter = 0;
  const registry = {}; // id -> element (also used by the extension to highlight findings)
  function idFor(el) {
    let id = el.getAttribute("data-darklens-id");
    if (!id) {
      counter += 1;
      id = "el-" + counter;
      el.setAttribute("data-darklens-id", id);
    }
    registry[id] = el;
    return id;
  }

  /** Collapse whitespace and cut to a maximum length. */
  function clean(text, max) {
    const t = (text || "").replace(/\s+/g, " ").trim();
    return t.length > (max || MAX_TEXT) ? t.slice(0, max || MAX_TEXT) : t;
  }

  /** True if the element is rendered and not hidden by CSS. */
  function isVisible(el) {
    if (!el || !el.isConnected) return false;
    if (el.checkVisibility) {
      if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
    } else {
      const s = cs(el);
      if (s.display === "none" || s.visibility === "hidden" || s.opacity === "0") return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  /** Computed style, using the element's own window (works inside same-origin iframes). */
  function cs(el) {
    return ((el.ownerDocument && el.ownerDocument.defaultView) || window).getComputedStyle(el);
  }

  /** Font size in px as a number. */
  function fontSize(el) {
    return parseFloat(cs(el).fontSize) || 0;
  }

  /** Is this element laid out as a block (paragraph, div, cell...) rather than inline text? */
  function isBlock(el) {
    const d = cs(el).display;
    return d !== "inline" && d !== "contents";
  }

  /** Parent element, stepping out of shadow roots and same-origin iframes. */
  function parentOf(el) {
    if (el.parentElement) return el.parentElement;
    const root = el.getRootNode && el.getRootNode();
    if (root && root.host) return root.host; // shadow root -> its host element
    return null;
  }

  /** The effective background colour: walk up until a non-transparent background is found. */
  function effectiveBg(el) {
    let cur = el;
    while (cur && cur.nodeType === 1) {
      const bg = cs(cur).backgroundColor;
      if (bg && bg !== "transparent" && !/rgba\(.*,\s*0\)$/.test(bg)) return bg;
      cur = parentOf(cur);
    }
    return "rgb(255, 255, 255)";
  }

  /** All documents/shadow roots we can read: the page, open shadow roots, same-origin iframes. */
  function allRoots() {
    const roots = [];
    const visit = (root) => {
      roots.push(root);
      root.querySelectorAll("*").forEach((el) => {
        if (el.shadowRoot) visit(el.shadowRoot); // open shadow DOM only
        if (el.tagName === "IFRAME") {
          try {
            const doc = el.contentDocument; // throws / null for cross-origin frames
            if (doc && doc.body) visit(doc);
          } catch (e) { /* cross-origin iframe: not readable, skip */ }
        }
      });
    };
    visit(document);
    return roots;
  }

  /** querySelectorAll across every readable root. */
  function queryAll(roots, selector) {
    const out = [];
    roots.forEach((r) => r.querySelectorAll(selector).forEach((el) => out.push(el)));
    return out;
  }

  // ------------------------------------------------------------------ popups

  /** Find overlays/dialogs: fixed (or absolute with high z-index) elements and role=dialog. */
  function findPopupElements(roots) {
    const found = [];
    const vw = window.innerWidth, vh = window.innerHeight;
    queryAll(roots, "body *").forEach((el) => {
      if (SKIP_TAGS.has(el.tagName)) return;
      const s = cs(el);
      const z = parseInt(s.zIndex, 10) || 0;
      const isDialog = el.getAttribute("role") === "dialog" || el.getAttribute("aria-modal") === "true" ||
        (el.tagName === "DIALOG" && el.open);
      const overlayish = s.position === "fixed" || s.position === "sticky" && z >= 100 || (s.position === "absolute" && z >= 100);
      if (!isDialog && !overlayish) return;
      if (!isVisible(el)) return;
      const r = el.getBoundingClientRect();
      if (r.width < 120 || r.height < 30) return; // tiny fixed widgets (chat bubbles) are not popups
      // Skip a header/nav bar stuck to the top that is not an overlay.
      if (!isDialog && (el.tagName === "HEADER" || el.tagName === "NAV") && r.top <= 0) return;
      // Keep only the outermost popup element.
      if (found.some((p) => p.contains(el))) return;
      found.push(el);
    });
    return found.map((el) => {
      const r = el.getBoundingClientRect();
      return { el, blocking: r.width >= vw * 0.6 && r.height >= vh * 0.6 };
    });
  }

  // ------------------------------------------------------------------ main collect()

  /**
   * Collect a PageSnapshot of the current page.
   * @param {string} collectorName "extension" or "playwright"
   * @returns {object} PageSnapshot (plain JSON object)
   */
  function collect(collectorName) {
    const t0 = performance.now();
    const roots = allRoots();
    let scanned = 0;

    // ---- popups first, so buttons/segments can say whether they are inside one
    const popupInfo = findPopupElements(roots);
    const popupOf = (el) => {
      for (const p of popupInfo) if (p.el === el || p.el.contains(el)) return p.el;
      return null;
    };
    const popups = popupInfo.map((p) => {
      const id = idFor(p.el);
      const shown = parseInt(p.el.getAttribute("data-darklens-shown") || "1", 10);
      return { id, text: clean(p.el.innerText, 500), is_blocking: p.blocking, times_shown: shown };
    });

    // ---- text segments: walk visible text nodes and group them by their nearest block element
    const blocks = new Map(); // block element -> { pieces: [], fine: [] }
    roots.forEach((root) => {
      const start = root.body || root; // document -> body, shadow root -> itself
      if (!start) return;
      const walker = document.createTreeWalker(start, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        scanned += 1;
        const txt = node.nodeValue.replace(/\s+/g, " ").trim();
        if (!txt) continue;
        const parent = node.parentElement;
        if (!parent || SKIP_TAGS.has(parent.tagName) || parent.closest("script,style,noscript,template")) continue;
        if (!isVisible(parent)) continue;
        let block = parent;
        while (block && !isBlock(block) && block.parentElement) block = block.parentElement;
        if (!blocks.has(block)) blocks.set(block, { pieces: [], fine: [] });
        const entry = blocks.get(block);
        entry.pieces.push(txt);
        const fs = fontSize(parent);
        if (fs > 0 && fs < FINE_PRINT_PX) entry.fine.push(txt);
      }
    });
    const segments = [];
    const seenText = new Set();
    for (const [block, entry] of blocks) {
      if (segments.length >= MAX_SEGMENTS) break;
      const text = clean(entry.pieces.join(" "));
      if (!text || seenText.has(text)) continue; // deduplicate identical text
      seenText.add(text);
      segments.push({
        id: idFor(block), tag: block.tagName.toLowerCase(), text, is_visible: true,
        font_size: fontSize(block), fine_print: entry.fine.length ? clean(entry.fine.join(" ")) : null,
      });
    }

    // ---- checkboxes and radio buttons (state + label only, never input values)
    const checkboxes = [];
    queryAll(roots, "input[type=checkbox], input[type=radio]").forEach((input) => {
      // The label may be hidden for custom switches, so check the label/parent visibility too.
      const label = (input.labels && input.labels[0]) || input.closest("label");
      if (!isVisible(input) && !(label && isVisible(label))) return;
      const labelText = clean(
        (label && label.innerText) || input.getAttribute("aria-label") ||
        (input.parentElement && input.parentElement.innerText) || "", 200);
      const fieldset = input.closest("fieldset");
      const legend = fieldset && fieldset.querySelector("legend");
      checkboxes.push({
        id: idFor(input), type: input.type, checked: !!input.checked, label: labelText,
        group: input.type === "radio" ? (input.name || null) : null,
        group_label: legend ? clean(legend.innerText, 150) : null,
        required: !!input.required,
      });
    });

    // ---- buttons and button-like links
    const buttonEls = queryAll(roots,
      "button, [role=button], input[type=submit], input[type=button], a[href]")
      .filter((el) => isVisible(el)).slice(0, MAX_BUTTONS);
    const buttonSet = new Set(buttonEls);
    const countButtonsIn = (el) => { let n = 0; buttonSet.forEach((b) => { if (el !== b && el.contains(b)) n += 1; }); return n; };
    const buttons = [];
    buttonEls.forEach((el) => {
      // Text: for <input type=submit> use its aria-label/title only (never read input values).
      const isInput = el.tagName === "INPUT";
      const text = clean(isInput ? (el.getAttribute("aria-label") || el.title || "submit") : el.innerText, 120);
      if (!text) return;
      const r = el.getBoundingClientRect();
      const s = cs(el);
      // Group = nearest ancestor (max 5 levels up) that contains at least one other button.
      let group = null, cur = parentOf(el);
      for (let depth = 0; cur && depth < 5; depth += 1, cur = parentOf(cur)) {
        if (cur === document.body) break;
        if (countButtonsIn(cur) >= 2) { group = cur; break; }
      }
      const popupEl = popupOf(el);
      const looksLikeButton = el.tagName !== "A" || (s.backgroundColor !== "rgba(0, 0, 0, 0)" && s.backgroundColor !== "transparent") || parseFloat(s.paddingTop) >= 6;
      buttons.push({
        id: idFor(el), text, width: Math.round(r.width), height: Math.round(r.height),
        font_size: fontSize(el), bg_color: effectiveBg(el), text_color: s.color,
        in_popup: !!popupEl, kind: looksLikeButton ? "button" : "link",
        group_id: group ? idFor(group) : null, popup_id: popupEl ? idFor(popupEl) : null,
      });
    });

    // ---- prices and timers: search the text of every visible text node
    const prices = [];
    const timers = [];
    roots.forEach((root) => {
      const start = root.body || root;
      if (!start) return;
      const walker = document.createTreeWalker(start, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        const txt = node.nodeValue;
        if (!txt || !/\d/.test(txt)) continue;
        const el = node.parentElement;
        if (!el || SKIP_TAGS.has(el.tagName) || !isVisible(el)) continue;

        // Prices
        const matches = txt.match(PRICE_RE);
        if (matches) {
          let struck = !!el.closest("del, s, strike");
          for (let a = el, i = 0; a && i < 3 && !struck; a = a.parentElement, i += 1) {
            if (cs(a).textDecorationLine.includes("line-through")) struck = true;
          }
          matches.forEach((raw) => {
            prices.push({
              id: idFor(el), raw_text: clean(raw, 40), value: simpleNumber(raw), currency: simpleCurrency(raw),
              struck_through: struck, context: priceContext(el, raw),
            });
          });
        }

        // Timers: clock-like text whose surrounding block mentions a deadline
        const tm = txt.match(TIMER_RE);
        if (tm) {
          // Look at the surrounding block (not just the span holding the digits).
          let block = el.parentElement || el;
          while (block.parentElement && !isBlock(block)) block = block.parentElement;
          const around = clean(block.innerText || "", 200);
          if (TIMER_CONTEXT_RE.test(around)) {
            timers.push({ id: idFor(el), raw_text: clean(tm[0], 40), seconds_left: toSeconds(tm[0]) });
          }
        }
      }
    });

    return {
      url: location.href,
      title: document.title || "",
      collected_at: new Date().toISOString(),
      collector: collectorName === "playwright" ? "playwright" : "extension",
      segments, checkboxes, buttons, prices, popups, timers,
      previous_prices: [],
      stats: { elements_scanned: scanned, duration_ms: Math.round(performance.now() - t0) },
    };
  }

  // ------------------------------------------------------------------ price / timer helpers
  // (The Python backend re-parses raw_text with its own, tested price parser.)

  /** "Rs 1,499.00" -> 1499 */
  function simpleNumber(raw) {
    const m = raw.replace(/,/g, "").match(/\d+(\.\d+)?/);
    return m ? parseFloat(m[0]) : null;
  }

  /** "₹" / "Rs" / "INR" -> "INR", "$" -> "USD", ... */
  function simpleCurrency(raw) {
    const r = raw.toUpperCase();
    if (r.includes("₹") || r.startsWith("RS") || r.startsWith("INR")) return "INR";
    if (r.includes("€") || r.startsWith("EUR")) return "EUR";
    if (r.includes("£") || r.startsWith("GBP")) return "GBP";
    if (r.includes("$") || r.startsWith("USD")) return "USD";
    return null;
  }

  /** Text of the row around a price, e.g. "Platform fee Rs 15.00" or the product name. */
  function priceContext(el, raw) {
    const row = el.closest("tr, li");
    if (row) return clean(row.innerText, 150);
    let cur = el;
    for (let i = 0; i < 4 && cur; i += 1) {
      const text = clean(cur.innerText || "", 300);
      if (text.replace(raw, "").replace(/[^A-Za-z]/g, "").length >= 20) return clean(text, 150);
      cur = cur.parentElement;
    }
    return clean((cur || el).innerText || "", 150);
  }

  /** "12:34" -> 754 seconds, "2h 15m" -> 8100, "5 mins left" -> 300 */
  function toSeconds(text) {
    const clock = text.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
    if (clock) {
      return clock[3] !== undefined
        ? (+clock[1]) * 3600 + (+clock[2]) * 60 + (+clock[3])
        : (+clock[1]) * 60 + (+clock[2]);
    }
    let total = 0;
    const h = text.match(/(\d+)\s*h/i); if (h) total += (+h[1]) * 3600;
    const m = text.match(/(\d+)\s*m(?!s)/i); if (m) total += (+m[1]) * 60;
    const s = text.match(/(\d+)\s*s(ec|econd)/i); if (s) total += +s[1];
    return total || null;
  }

  // Public API
  window.DarkLensCollector = {
    collect,
    /** Look up an element by its data-darklens-id (also inside shadow roots / iframes). */
    elementFor: (id) => registry[id] || document.querySelector('[data-darklens-id="' + id + '"]'),
  };
})();
