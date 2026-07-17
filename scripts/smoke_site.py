"""Cross-engine smoke test for a built site page (dev-only; needs playwright).

Repo-agnostic by design: expectations are read from the page's own payload,
so the same script verifies any deployment (FastVideo, ComfyUI, future repos).

Checks per engine (chromium, webkit, firefox) x (normal, reduced-motion):
hero-first layout, the guess beat plays and claims the measured correlation,
the org-lens section renders with the sim's real numbers, the curated compare
deep link opens the dialog, the Ctrl/Cmd+K palette opens/jumps/closes with the
Escape cascade intact, and the page throws zero errors.

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
    # a payload-derived contributor for the palette scenario (not rank 1, so a
    # working jump can't be confused with a default state)
    pal_author = payload["authors"][min(2, len(payload["authors"]) - 1)]["name"]

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

                # command palette: Ctrl+K opens, a typed contributor jumps to
                # their open detail row, Escape closes the palette itself
                # (cascade order: the compare modal must stay untouched)
                pg.keyboard.press("Control+k")
                pg.wait_for_timeout(250)
                if not pg.eval_on_selector("#palette", VIS):
                    fails.append(f"[{tag}] palette did not open on Ctrl+K")
                else:
                    if not pg.eval_on_selector("#nav-kbd", VIS):
                        fails.append(f"[{tag}] nav palette affordance hidden")
                    pg.fill("#palette-input", pal_author)
                    pg.wait_for_timeout(150)
                    pg.keyboard.press("Enter")
                    pg.wait_for_timeout(500)
                    if pg.eval_on_selector("#palette", VIS):
                        fails.append(f"[{tag}] palette still open after Enter")
                    row_btn = f'tr.row[data-name="{pal_author}"] .row-btn'
                    if pg.eval_on_selector(
                        row_btn, "el=>el.getAttribute('aria-expanded')"
                    ) != "true":
                        fails.append(f"[{tag}] palette jump left detail closed")
                    pg.keyboard.press("Control+k")
                    pg.wait_for_timeout(250)
                    pg.keyboard.press("Escape")
                    pg.wait_for_timeout(150)
                    if pg.eval_on_selector("#palette", VIS):
                        fails.append(f"[{tag}] Escape did not close the palette")
                    if pg.eval_on_selector("#compare", VIS):
                        fails.append(f"[{tag}] Escape leaked past the palette")

                # shortcuts legend: ? opens, Escape closes
                pg.keyboard.press("?")
                pg.wait_for_timeout(250)
                if not pg.eval_on_selector("#legend", VIS):
                    fails.append(f"[{tag}] legend did not open on ?")
                pg.keyboard.press("Escape")
                pg.wait_for_timeout(150)
                if pg.eval_on_selector("#legend", VIS):
                    fails.append(f"[{tag}] Escape did not close the legend")

                # hint beacons: appear once the field is on screen; the tip
                # opens on click and its ✕ removes the beacon for good
                pg.eval_on_selector(
                    "#field", "el=>el.scrollIntoView({behavior:'instant',block:'center'})"
                )
                pg.wait_for_timeout(600)
                beacon = '[data-hint="dotkeys"]'
                if not pg.query_selector(beacon):
                    fails.append(f"[{tag}] dotkeys beacon absent")
                else:
                    pg.click(beacon)
                    pg.wait_for_timeout(200)
                    if not pg.eval_on_selector(".beacon-tip", VIS):
                        fails.append(f"[{tag}] beacon tip did not open")
                    pg.click(".beacon-tip-x")
                    pg.wait_for_timeout(150)
                    if pg.query_selector(beacon):
                        fails.append(f"[{tag}] dismissed beacon still present")
                    elif engine == "chromium":
                        # persistence asserted on chromium only: webkit and
                        # firefox deny storage on file:// and fall back to
                        # the in-memory latch (hints return per load there)
                        pg.reload()
                        pg.wait_for_timeout(600)
                        pg.eval_on_selector(
                            "#field",
                            "el=>el.scrollIntoView({behavior:'instant',block:'center'})",
                        )
                        pg.wait_for_timeout(600)
                        if pg.query_selector(beacon):
                            fails.append(f"[{tag}] beacon returned after reload")

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
