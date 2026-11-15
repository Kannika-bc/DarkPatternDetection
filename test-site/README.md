# DarkLens test site

Fictional websites with **planted** dark patterns, used to develop and evaluate the extension.
All brands (Tiffinly, Kartiq, Yatrly, StreamBox, The Daily Ledger, FairMart) are made up.

| Folder | Category | Pages | Planted |
|---|---|---|---|
| `food/` | Food delivery (Tiffinly) | menu (product), cart | 8 |
| `shop/` | E-commerce (Kartiq) | product, cart, checkout | 10 |
| `travel/` | Travel (Yatrly) | flights (product), booking (checkout) | 11 |
| `ott/` | OTT / subscriptions (StreamBox) | plans, signup, account/cancel | 7 |
| `news/` | News (The Daily Ledger) | article (+ iframe ad) | 6 |
| `clean/` | Honest store (FairMart) | product, cart, signup, plans, article | **0** (17 hard negatives) |

## Run it

Plain HTML/CSS/JS, no build step. From the repo root:

```bash
python -m http.server 8090 --directory test-site
```

Then open <http://localhost:8090/>. (Port 8080 is used by another program on the dev laptop.) (Use a server rather than double-clicking files, because the
extension and the iframe behave differently on `file://` URLs.)

## Ground truth

`ground-truth.json` lists every planted pattern with its page, type, CCPA ref, CSS selector, phase
(MVP/V2), evidence kind and expected status, plus the page type of each page (for evaluating the
page-type detector) and **hard negatives**: honest elements on the clean site that look a bit like a
dark pattern and must *not* be flagged.

Check that the ground truth still matches the pages after any edit:

```bash
python test-site/check_ground_truth.py
```

## Robustness cases covered

| Case | Where |
|---|---|
| Timer that resets on reload | `shop/product.html`, `travel/flights.html` |
| Random "live" counts | `shop/product.html`, `travel/flights.html` |
| Content injected after load | `food/menu.html` (2 s), popups on several pages |
| SPA URL change (`history.pushState`) | `food/menu.html` tabs |
| Open Shadow DOM | `shop/product.html` (`<kartiq-recommendations>`) |
| Same-origin iframe | `news/article.html` → `news/ad-frame.html` |
| Repeated popups (nagging) | `food/menu.html`, `news/article.html` |
| Cross-page price change | `shop/product` → `shop/cart` (₹1,499 → ₹1,799) |
| Currency formats | Rs, ₹, INR, Rs., €, £, US$ with Indian and western digit grouping |
| Pre-filled personal data (must never be read) | `shop/checkout.html`, `ott/signup.html`, `clean/signup.html` |

## Rules
- **Detectors must never use these ids, class names, brand names or this file.** They exist only so the
  evaluation script can match findings to planted elements. Detection must stay generic (hard rule 1).
- When you add or change a planted pattern, update `ground-truth.json` and re-run the checker.
