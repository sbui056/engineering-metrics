"""Cross-engine smoke test for a built site page (dev-only; needs playwright).

Repo-agnostic by design: expectations are read from the page's own payload,
so the same script verifies any deployment (FastVideo, ComfyUI, future repos).

Checks per engine (chromium, webkit, firefox) x (normal, reduced-motion):
hero-first layout, the guess beat plays and claims the measured correlation,
the org-lens section renders with the sim's real numbers, the curated compare
deep link opens the dialog, and the page throws zero errors.

Assertion style matters (hard-won): computed visibility, never the `hidden`
attribute; `offsetParent` is null for position:fixed elements.

Usage: python scripts/smoke_site.py [path/to/index.html]   (default: dist/index.html)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

VIS = (
    "el=>{const s=getComputedStyle(el);"
    "return !el.hasAttribute('hidden') && s.display!=='none' && "
    "s.visibility!=='hidden' && el.getBoundingClientRect().height>0;}"
)


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright not installed — `pip install playwright` (dev-only)")

    page_path = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/index.html").resolve()
    if not page_path.exists():
        sys.exit(f"{page_path} not found — run `make site` first")
    url = page_path.as_uri()

    html = page_path.read_text(encoding="utf-8")
    payload = json.loads(
        re.search(r"window.__DATA__ = (\{.*?\});</script>", html, re.S).group(1)
    )
    rho = f"{payload['meta']['rho']:.2f}"
    top_risk = max(payload["org"]["risk"].items(), key=lambda kv: kv[1]["files"])
    top_name, top = top_risk

    fails: list[str] = []
    with sync_playwright() as p:
        for engine in ("chromium", "webkit", "firefox"):
            browser = getattr(p, engine).launch()
            for reduced in (False, True):
                tag = f"{engine}{'/reduced' if reduced else ''}"
                ctx = browser.new_context(
                    reduced_motion="reduce" if reduced else "no-preference",
                    viewport={"width": 1280, "height": 900},
                )
                pg = ctx.new_page()
                errs: list[str] = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(url)
                pg.wait_for_timeout(800)

                # hero first; the beat's interactive controls below the fold
                if pg.eval_on_selector("#top", "el=>el.getBoundingClientRect().top") > 200:
                    fails.append(f"[{tag}] hero not at top")
                probe = "#prologue-result" if reduced else "#prologue-range"
                if pg.eval_on_selector(probe, "el=>el.getBoundingClientRect().top") < 900:
                    fails.append(f"[{tag}] beat controls inside first viewport")

                # the beat claims the measured correlation
                pg.eval_on_selector(
                    "#prologue", "el=>el.scrollIntoView({behavior:'instant',block:'center'})"
                )
                pg.wait_for_timeout(250)
                if not reduced:
                    pg.click("#prologue-reveal")
                    pg.wait_for_timeout(250)
                if rho not in pg.inner_text("#prologue-readout"):
                    fails.append(f"[{tag}] prologue rho != {rho}")

                # org lens renders the payload's own numbers
                pg.eval_on_selector(
                    "#team", "el=>el.scrollIntoView({behavior:'instant',block:'start'})"
                )
                pg.wait_for_timeout(500)
                if "over half" not in pg.inner_text("#org-headline"):
                    fails.append(f"[{tag}] org headline missing")
                readout = pg.inner_text("#sim-readout")
                if f"{top['files']} file" not in readout:
                    fails.append(f"[{tag}] sim != {top_name}'s {top['files']} files")

                # curated compare link opens the dialog
                pg.eval_on_selector(
                    "#leaderboard", "el=>el.scrollIntoView({behavior:'instant'})"
                )
                pg.wait_for_timeout(250)
                pg.click(".section-sub .pointer-link")
                pg.wait_for_timeout(700)
                if not pg.eval_on_selector("#compare", VIS):
                    fails.append(f"[{tag}] compare deep link failed")
                pg.keyboard.press("Escape")

                if errs:
                    fails.append(f"[{tag}] page errors: {errs}")
                else:
                    print(f"[{tag}] OK")
                ctx.close()
            browser.close()

    if fails:
        print("\nFAILURES:\n" + "\n".join(fails))
        sys.exit(1)
    print(f"\nALL CHECKS PASSED — {page_path.name} "
          f"({payload['meta']['repo']}, N={payload['meta']['n_authors']})")


if __name__ == "__main__":
    main()
