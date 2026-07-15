"""Playwright smoke for the essay page (dist/ preview or docs/ deploy).

Usage: python scripts/smoke_essay.py [path/to/index.html]

Checks, per engine (chromium, webkit, firefox): the page loads from file://
with zero console errors, all four figures render, the margin-note rail and
paired panel are present, and a 390px viewport shows no horizontal scroll.
The page is static HTML, so there is no JS or reduced-motion surface to probe.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "dist" / "two-org-shapes" / "index.html"


def check(browser_type, url: str) -> list[str]:
    problems: list[str] = []
    browser = browser_type.launch()
    try:
        page = browser.new_page(viewport={"width": 1180, "height": 900})
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.wait_for_timeout(300)

        if errors:
            problems.append(f"console errors: {errors[:3]}")
        for sel, want in [("svg", 4), ("aside.mn", None), (".pair", 1),
                          ("h1", 1), (".colophon a", None)]:
            n = page.locator(sel).count()
            if (want is not None and n != want) or (want is None and n == 0):
                problems.append(f"{sel}: found {n}, wanted {want or '>=1'}")
        if page.evaluate("document.title").strip() in ("", "·"):
            problems.append("empty <title>")

        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile.goto(url)
        mobile.wait_for_timeout(300)
        overflow = mobile.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth")
        if overflow > 1:
            problems.append(f"mobile horizontal overflow: {overflow}px")
    finally:
        browser.close()
    return problems


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not target.exists():
        sys.exit(f"smoke_essay: {target} not found (run build_essay.py first)")
    url = target.resolve().as_uri()

    failed = False
    with sync_playwright() as p:
        for bt in (p.chromium, p.webkit, p.firefox):
            problems = check(bt, url)
            status = "OK" if not problems else "FAIL " + "; ".join(problems)
            print(f"[{bt.name}] {status}")
            failed = failed or bool(problems)
    if failed:
        sys.exit(1)
    print(f"\nALL CHECKS PASSED — {target}")


if __name__ == "__main__":
    main()
