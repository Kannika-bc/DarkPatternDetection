// DarkLens background service worker.
// Jobs: (1) send snapshots to the local Python backend, (2) show the number of findings on the
// toolbar badge. The content script asks us to do the network call because an extension's
// background worker is allowed to call http://localhost:8000 from any website.

const BACKEND = "http://localhost:8000";

/**
 * Send a PageSnapshot to POST /analyze and return the JSON answer
 * (or { error: "..." } if the backend is not running).
 */
async function analyzeSnapshot(snapshot) {
  try {
    const response = await fetch(BACKEND + "/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(snapshot),
    });
    if (!response.ok) {
      return { error: "Backend error " + response.status + ": " + (await response.text()).slice(0, 300) };
    }
    return await response.json();
  } catch (e) {
    return { error: "backend-offline" };
  }
}

/** Show the number of findings on the toolbar icon of one tab (red if any, green if 0). */
function setBadge(tabId, result) {
  if (tabId === undefined) return;
  let text = "";
  let color = "#9ca3af";
  if (result && result.error) {
    text = "off";
  } else if (result && result.findings) {
    text = String(result.findings.length);
    color = result.findings.length ? "#dc2626" : "#16a34a";
  }
  chrome.action.setBadgeText({ tabId, text });
  chrome.action.setBadgeBackgroundColor({ tabId, color });
}

// Messages from content scripts: { type: "analyze", snapshot }
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === "analyze") {
    analyzeSnapshot(message.snapshot).then((result) => {
      setBadge(sender.tab && sender.tab.id, result);
      sendResponse(result);
    });
    return true; // keep the channel open for the async answer
  }
  return false;
});
