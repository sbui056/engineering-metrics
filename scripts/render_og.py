"""Render dist/og.png — the one static Open Graph image (1200x630).

Loads the already-built dist/index.html in headless Chrome, hides the nav and
CTAs, and captures the hero (title + arcs + formula) at OG dimensions. Run via
`make og` after `make site`; requires playwright (dev-only dependency — the
image is crawler-fetched, never a page resource, so index.html stays
self-contained without it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "index.html"
OUT = ROOT / "dist" / "og.png"


def main() -> None:
    if not DIST.exists():
        sys.exit("dist/index.html not found — run `make site` first")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright not installed — `pip install playwright` (dev-only)")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")  # local dev
        except Exception:
            browser = p.chromium.launch()  # CI: playwright-installed chromium
        page = browser.new_page(
            viewport={"width": 1200, "height": 630}, device_scale_factor=2
        )
        page.goto(DIST.as_uri())
        page.wait_for_timeout(2500)  # arcs drawn, reveals settled
        page.evaluate(
            """() => {
              document.querySelector('.nav').style.display = 'none';
              document.querySelector('.hero-ctas').style.display = 'none';
              const inner = document.querySelector('.hero-inner');
              inner.style.paddingTop = '5.5rem';
              window.scrollTo(0, 0);
            }"""
        )
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT), clip={"x": 0, "y": 0, "width": 1200, "height": 630})
        browser.close()
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
