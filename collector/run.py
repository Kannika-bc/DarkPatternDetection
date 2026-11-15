"""CLI: collect one page and save its PageSnapshot as JSON.

    python -m collector.run --url http://localhost:8090/shop/product.html --out snapshot.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from collector.playwright_collector import collect_url


def main() -> None:
    parser = argparse.ArgumentParser(description="DarkLens Playwright collector")
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", default="snapshot.json")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--settle-ms", type=int, default=3000)
    parser.add_argument("--no-reload-check", action="store_true", help="skip the timer reset check")
    args = parser.parse_args()

    snap = collect_url(args.url, headless=not args.headed, settle_ms=args.settle_ms,
                       check_reload=not args.no_reload_check)
    Path(args.out).write_text(snap.model_dump_json(indent=2), encoding="utf-8")
    print(f"Saved {args.out}: {len(snap.segments)} segments, {len(snap.checkboxes)} checkboxes, "
          f"{len(snap.buttons)} buttons, {len(snap.prices)} prices, {len(snap.popups)} popups, "
          f"{len(snap.timers)} timers ({snap.stats.duration_ms if snap.stats else '?'} ms in page)")


if __name__ == "__main__":
    main()
