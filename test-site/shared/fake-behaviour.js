// DarkLens test site — helpers that simulate common *behavioural* dark patterns.
// These are deliberately deceptive so the extension has something to detect.

// FAKE TIMER: the deadline is "now + minutes" on every page load,
// so the countdown restarts whenever the page is reloaded.
function startResettingTimer(elementId, minutes) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const deadline = Date.now() + minutes * 60 * 1000;
  const tick = () => {
    const left = Math.max(0, deadline - Date.now());
    const m = String(Math.floor(left / 60000)).padStart(2, "0");
    const s = String(Math.floor((left % 60000) / 1000)).padStart(2, "0");
    el.textContent = `${m}:${s}`;
  };
  tick();
  setInterval(tick, 1000);
}

// FAKE SOCIAL PROOF: a "live" count that is just a random number each load.
function randomCount(elementId, min, max) {
  const el = document.getElementById(elementId);
  if (el) el.textContent = String(min + Math.floor(Math.random() * (max - min + 1)));
}

// NAGGING: show a popup again `delayMs` after every time it is closed.
function nagRepeatedly(overlayId, closeButtonIds, delayMs) {
  const overlay = document.getElementById(overlayId);
  if (!overlay) return;
  const show = () => overlay.classList.remove("hidden");
  closeButtonIds.forEach((id) => {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener("click", () => {
      overlay.classList.add("hidden");
      setTimeout(show, delayMs);
    });
  });
}

// Close an overlay without re-showing it.
function closeOnClick(overlayId, buttonIds) {
  const overlay = document.getElementById(overlayId);
  buttonIds.forEach((id) => {
    const btn = document.getElementById(id);
    if (btn && overlay) btn.addEventListener("click", () => overlay.classList.add("hidden"));
  });
}
