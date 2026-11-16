// DarkLens popup: shows the trust score and findings of the current tab and sends commands
// ("show", "fix", "fixAll", "rescan", "download") to the content script running in that tab.

/** Get the id of the tab the user is looking at. */
async function activeTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab && tab.id;
}

/** Send a command to the content script of the active tab and return its answer. */
async function send(cmd, extra) {
  const tabId = await activeTabId();
  try {
    return await chrome.tabs.sendMessage(tabId, Object.assign({ cmd }, extra || {}));
  } catch (e) {
    return { error: "no-content-script" }; // e.g. chrome:// pages, or the page was opened before install
  }
}

/** Create an element with a class and text (safe: text is never parsed as HTML). */
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/** Draw the result (trust score + list of findings) in the popup. */
function render(result) {
  const offline = document.getElementById("offline");
  const summary = document.getElementById("summary");
  const list = document.getElementById("findings");
  const empty = document.getElementById("empty");
  list.innerHTML = "";
  offline.classList.add("hidden");
  summary.classList.add("hidden");
  empty.classList.add("hidden");

  if (!result || result.error) {
    if (result && result.error === "no-content-script") {
      empty.textContent = "DarkLens cannot run on this page. Reload the page and try again.";
      empty.classList.remove("hidden");
    } else if (result && result.error === "backend-offline") {
      offline.classList.remove("hidden");
    } else {
      empty.textContent = result && result.error ? result.error : "Scanning... click Re-scan in a moment.";
      empty.classList.remove("hidden");
    }
    document.getElementById("fixAll").disabled = true;
    return;
  }

  summary.classList.remove("hidden");
  const score = document.getElementById("score");
  score.textContent = result.trust_score;
  score.parentElement.className = "score " + (result.trust_score >= 80 ? "good" : result.trust_score >= 50 ? "mid" : "bad");
  document.getElementById("pageinfo").textContent =
    "Page type: " + result.page_type + " · " + result.findings.length + " finding(s)";

  const fixable = result.findings.filter((f) => f.fixable).length;
  document.getElementById("fixAll").disabled = fixable === 0;
  if (!result.findings.length) empty.classList.remove("hidden");

  result.findings.forEach((f, index) => {
    const li = el("li");
    const head = el("div");
    head.appendChild(el("span", "type", f.type.replace(/_/g, " ")));
    head.appendChild(el("span", "tag", f.ccpa_ref ? "CCPA " + f.ccpa_ref : "extra"));
    head.appendChild(el("span", "tag " + f.severity, f.severity));
    head.appendChild(el("span", "tag", f.status));
    li.appendChild(head);
    li.appendChild(el("div", "evidence", "“" + f.text.slice(0, 140) + "”"));
    li.appendChild(el("div", "why", f.explanation));
    const row = el("div", "row");
    const show = el("button", "", "Show");
    show.onclick = () => send("show", { index });
    row.appendChild(show);
    if (f.fixable) {
      const fix = el("button", "primary", "Fix");
      fix.onclick = async () => {
        const r = await send("fix", { index });
        fix.textContent = r && r.ok ? "Fixed ✓" : "Could not fix";
        fix.disabled = true;
      };
      row.appendChild(fix);
    }
    li.appendChild(row);
    document.getElementById("findings").appendChild(li);
  });
}

document.getElementById("rescan").onclick = async () => render(await send("rescan"));
document.getElementById("download").onclick = () => send("download");
document.getElementById("fixAll").onclick = async () => {
  const r = await send("fixAll");
  document.getElementById("fixAll").textContent = "Fixed " + ((r && r.fixed) || 0);
};

// When the popup opens: show the latest result (or trigger a scan if there is none yet).
(async () => {
  const result = await send("get");
  if (result && !result.error && result.findings) render(result);
  else render(await send("rescan"));
})();
