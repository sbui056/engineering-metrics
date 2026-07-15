"""Build the "Two org shapes" essay page from the reviewed draft.

Manual authoring tool, never run in CI. Inputs are the draft markdown
(drafts/two-org-shapes-draft.md), the extracted numbers (drafts/numbers.json,
produced by essay_numbers.py) and the deployed dashboard payloads; the output
is one self-contained HTML page plus an OG card.

Publishing gate: while numbers.json carries FROZEN:false the output goes to
dist/two-org-shapes/ (preview) and writing docs/ is refused, so a page with
provisional numbers cannot ship by accident. After the freeze rerun of
essay_numbers.py the same command writes docs/two-org-shapes/.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "drafts" / "two-org-shapes-draft.md"
NUMBERS = ROOT / "drafts" / "numbers.json"
TEMPLATE = ROOT / "site" / "src" / "essay.html"
ESSAY_CSS = ROOT / "site" / "src" / "essay.css"
SITE_CSS = ROOT / "site" / "src" / "styles.css"
SLUG = "two-org-shapes"

DEFAULT_URL = "https://sbui056.github.io/engineering-metrics/two-org-shapes/"

PAYLOAD_RE = re.compile(r"window\.__DATA__\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S)
MARKER_RE = re.compile(r"\s*\[(?:PROVISIONAL|VERIFY)[^\]]*\]")

# ---- palette (mirrors :root in styles.css; figures inline their own fills) ----
PAPER, CREAM, PUTTY = "#FBFAF6", "#F3F1EB", "#E3DAD3"
INK, INK2, INK3 = "#1A1512", "#5A544B", "#736D65"
ESPRESSO, RUST, BLUE = "#43262B", "#D64A22", "#3563C9"
GRID = "rgba(26,21,18,0.09)"
HAIR2 = "rgba(26,21,18,0.16)"
MONO = "'Fragment Mono',ui-monospace,'SF Mono',Menlo,monospace"
UI = "'Inter',system-ui,sans-serif"

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
         6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


# --------------------------------------------------------------------- inputs
def load_payload(path: Path) -> dict:
    return json.loads(PAYLOAD_RE.search(path.read_text()).group(1))


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def tool_repo_url() -> str:
    url = os.environ.get("TOOL_URL", "").strip()
    if url:
        return url
    try:
        raw = subprocess.run(["git", "-C", str(ROOT), "config", "--get", "remote.origin.url"],
                             capture_output=True, text=True, check=True).stdout.strip()
        raw = re.sub(r"\.git$", "", raw)
        m = re.match(r"git@github\.com:(.+)", raw)
        return f"https://github.com/{m.group(1)}" if m else raw
    except subprocess.CalledProcessError:
        return ""


# ----------------------------------------------------------- markdown (strict)
def split_blocks(text: str) -> list[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


def render_inline(s: str) -> str:
    s = esc(s.replace("\n", " "))
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"<em>\1</em>", s)
    for tok in ("**", "]("):
        if tok in s:
            sys.exit(f"build_essay: unconverted markdown {tok!r} in: {s[:90]}...")
    return s


def parse_draft(text: str, frozen: bool, freeze_date: str):
    """Return (title, dek, stamp, body_blocks) where body_blocks are tagged."""
    if frozen:
        leftover = MARKER_RE.findall(text) + (["[FREEZE-DATE]"] if "[FREEZE-DATE]" in text else [])
        if leftover:
            sys.exit(f"build_essay: frozen build but draft still carries markers: {leftover[:4]}")
    else:
        text = MARKER_RE.sub("", text)
        text = text.replace("[FREEZE-DATE]", f"{freeze_date} (preview, numbers not frozen)")

    blocks = split_blocks(text)
    if not blocks[0].startswith("# "):
        sys.exit("build_essay: draft must open with an h1 title")
    title = blocks[0][2:].strip()
    dek = blocks[1].strip("*").strip()
    stamp = blocks[2].strip("*").strip()
    if blocks[3] != "---":
        sys.exit("build_essay: expected --- after the masthead blocks")

    body = []
    pair_buf = None
    for b in blocks[4:]:
        if "[FOOTER" in b:
            continue
        if b == "<!--pair-->":
            if pair_buf is not None:
                sys.exit("build_essay: nested <!--pair--> fence")
            pair_buf = []
            continue
        if b == "<!--/pair-->":
            if pair_buf is None or len(pair_buf) != 2:
                sys.exit("build_essay: <!--/pair--> needs exactly two paragraphs inside")
            body.append(("pair", pair_buf))
            pair_buf = None
            continue
        if pair_buf is not None:
            pair_buf.append(b)
            continue
        if b.startswith("## "):
            body.append(("h2", b[3:].strip()))
        elif b == "---":
            body.append(("hr", ""))
        elif re.match(r"\[FIGURE (\d+):", b):
            body.append(("figure", int(re.match(r"\[FIGURE (\d+):", b).group(1))))
        elif all(line.startswith("- ") for line in b.splitlines()):
            body.append(("ul", [line[2:] for line in b.splitlines()]))
        elif b.startswith(("#", ">", "```")) or re.match(r"\d+\. ", b):
            sys.exit(f"build_essay: unsupported markdown block: {b[:60]}...")
        else:
            body.append(("p", b))
    if pair_buf is not None:
        sys.exit("build_essay: unclosed <!--pair--> fence")
    return title, dek, stamp, body


# ------------------------------------------------------------------- sidenotes
def sidenotes(n: dict) -> list[dict]:
    """Margin-rail notes: anchor phrase (must appear in exactly one paragraph),
    a mono label, and one plain sentence. Values come from numbers.json."""
    fv, cu = n["fastvideo"], n["comfyui"]
    ez = n["f3"]["enzymezoo"]
    oc = fv["one_commit"]
    return [
        {"anchor": "a rank correlation of",
         "label": f"ρ = {fv['meta']['rho']:.2f} / {cu['meta']['rho']:.2f}",
         "text": "Spearman rank correlation between the commit-count ranking and the "
                 "impact ranking, computed per repository from the page payloads."},
        {"anchor": "of all the code that survives",
         "label": f"{round(cu['top1_share'] * 100)}%",
         "text": "share of surviving lines attributed to one author by git blame at "
                 "HEAD, with whitespace and copy detection on."},
        {"anchor": "averaged with equal weights",
         "label": "0.25 × 4",
         "text": "the score is the average of four percentiles; the weighting is "
                 "disclosed as a choice rather than presented as tuned."},
        {"anchor": "contributors with exactly one commit",
         "label": f"{oc['count']} tie at #{oc['tie_rank']}",
         "text": "by commit count every one-commit contributor shares one rank; their "
                 "impact ranks are read from the same payload."},
        {"anchor": "they settled at",
         "label": f"#{ez['rank_imputed']} → #{ez['rank_complete']}",
         "text": "ranks read from the partial-data page and the complete-data "
                 "analysis; both states shipped with the estimation badge visible."},
        {"anchor": "computed from the repository at build time",
         "label": "provenance",
         "text": "every number in this essay was generated by the build script from "
                 "the dashboards' data payloads; none was typed by hand."},
    ]


# --------------------------------------------------------------------- figures
def _t(x, y, s, size=11, fill=INK2, anchor="start", weight=400, mono=False, dy=0):
    fam = MONO if mono else UI
    return (f'<text x="{x:.1f}" y="{y + dy:.1f}" font-family="{fam}" font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}">{esc(s)}</text>')


def _scatter_panel(ox, rows, title, rho, callouts, W=330, H=290):
    ml, mr, mt, mb = 40, 12, 44, 34
    pw, ph = W - ml - mr, H - mt - mb
    xmax = math.log10(3200)

    def X(c): return ox + ml + (math.log10(max(c, 1)) / xmax) * pw
    def Y(v): return mt + (1 - v) * ph

    s = [_t(ox + ml, 16, title, 12.5, INK, weight=600),
         _t(ox + ml, 32, f"rank correlation {rho:.2f}", 11, INK2, mono=True)]
    for gv in (0, 0.25, 0.5, 0.75, 1.0):
        y = Y(gv)
        s.append(f'<line x1="{ox+ml}" y1="{y:.1f}" x2="{ox+ml+pw}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        s.append(_t(ox + ml - 6, y, f"{gv:g}", 10, INK3, anchor="end", dy=3.5, mono=True))
    for tx in (1, 10, 100, 1000):
        s.append(_t(X(tx), mt + ph + 16, f"{tx:,}", 10, INK3, anchor="middle", mono=True))
    s.append(_t(ox + ml + pw / 2, mt + ph + 30, "commits (log scale)", 10.5, INK3, anchor="middle"))
    if ox == 0:
        s.append(f'<text x="{ox+12}" y="{mt + ph/2:.1f}" font-family="{UI}" font-size="10.5" '
                 f'fill="{INK3}" text-anchor="middle" transform="rotate(-90 {ox+12} {mt+ph/2:.1f})">impact score</text>')
    call_names = {c[0] for c in callouts}
    alpha = 0.32 if len(rows) < 150 else 0.22
    for r in rows:
        if r["name"] in call_names:
            continue
        s.append(f'<circle cx="{X(r["commits"]):.1f}" cy="{Y(r["impact"]):.1f}" r="3.2" '
                 f'fill="{INK}" fill-opacity="{alpha}"><title>{esc(r["name"])}: '
                 f'{r["commits"]} commits, impact {r["impact"]:.3f}, rank {r["rank"]}</title></circle>')
    for name, dx, dy_, anchor in callouts:
        r = next(x for x in rows if x["name"] == name)
        cx, cy = X(r["commits"]), Y(r["impact"])
        s.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.6" fill="{RUST}" stroke="{PAPER}" stroke-width="2">'
                 f'<title>{esc(name)}: {r["commits"]} commits, impact {r["impact"]:.3f}, rank {r["rank"]}</title></circle>')
        s.append(_t(cx + dx, cy + dy_, f"{name} · #{r['rank']}", 10.5, INK, anchor=anchor, weight=600))
    return "".join(s)


def fig_scatters(fv, cu, n):
    body = (_scatter_panel(0, fv["authors"], f"FastVideo · {len(fv['authors'])} contributors",
                           fv["meta"]["rho"], [("alexzms", -8, -8, "end"), ("William Lin", -10, 16, "end")])
            + _scatter_panel(360, cu["authors"], f"ComfyUI · {len(cu['authors'])} contributors",
                             cu["meta"]["rho"], [("comfyanonymous", -10, -8, "end"), ("guill", 9, -6, "start")]))
    return f'<svg viewBox="0 0 700 290" role="img" aria-label="Commits versus impact score, one panel per repository">{body}</svg>'


def _lorenz_panel(ox, curve, title, gini, hold, hold_label, W=330, H=290):
    ml, mr, mt, mb = 40, 12, 44, 34
    pw, ph = W - ml - mr, H - mt - mb
    n = len(curve)

    def X(i): return ox + ml + (i / n) * pw
    def Y(v): return mt + (1 - v) * ph

    pts = [(X(0), Y(0))] + [(X(i + 1), Y(v)) for i, v in enumerate(curve)]
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = path + f" L{X(n):.1f},{Y(1):.1f} L{X(0):.1f},{Y(0):.1f} Z"
    s = [_t(ox + ml, 16, title, 12.5, INK, weight=600),
         _t(ox + ml, 32, f"Gini {gini:.2f}", 11, INK2, mono=True)]
    for gv in (0, 0.5, 1.0):
        y = Y(gv)
        s.append(f'<line x1="{ox+ml}" y1="{y:.1f}" x2="{ox+ml+pw}" y2="{y:.1f}" stroke="{GRID}"/>')
        s.append(_t(ox + ml - 6, y, f"{int(gv*100)}%", 10, INK3, anchor="end", dy=3.5, mono=True))
    s.append(f'<path d="{area}" fill="{PUTTY}" fill-opacity="0.45"/>')
    s.append(f'<line x1="{X(0):.1f}" y1="{Y(0):.1f}" x2="{X(n):.1f}" y2="{Y(1):.1f}" '
             f'stroke="{INK3}" stroke-width="1" stroke-dasharray="4 4"/>')
    s.append(f'<path d="{path}" fill="none" stroke="{ESPRESSO}" stroke-width="2"/>')
    hx, hy = X(hold), Y(curve[hold - 1])
    s.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="4.6" fill="{RUST}" stroke="{PAPER}" stroke-width="2"/>')
    s.append(_t(hx + 9, hy + 4, hold_label, 10.5, INK, weight=600))
    s.append(_t(ox + ml + pw / 2, mt + ph + 16, "contributors, largest owners first", 10.5, INK3, anchor="middle"))
    return "".join(s)


def fig_lorenz(fv, cu, n):
    fvn, cun = n["fastvideo"], n["comfyui"]
    fv_label = f"{WORDS.get(fvn['hold_half'], fvn['hold_half'])} people hold half"
    cu_hold = cun["hold_half"]
    cu_label = (f"one person holds {round(cun['top1_share'] * 100)}%" if cu_hold == 1
                else f"{WORDS.get(cu_hold, cu_hold)} people hold half")
    body = (_lorenz_panel(0, fv["org"]["curve"], "FastVideo", fv["org"]["gini"], fvn["hold_half"], fv_label)
            + _lorenz_panel(360, cu["org"]["curve"], "ComfyUI", cu["org"]["gini"], max(cu_hold, 1), cu_label))
    return (f'<svg viewBox="0 0 700 290" role="img" aria-label="Cumulative share of surviving code, '
            f'one Lorenz curve per repository">{body}</svg>')


def fig_dumbbell(fv, cu, n):
    movers = n["f3"]["movers"]
    ez = n["f3"]["enzymezoo"]
    rows = [m for m in movers if m["rank_complete"] <= 60 or abs(m["shift"]) >= 100][:9]
    rows.append({"name": "enzymezoo-code", "rank_imputed": ez["rank_imputed"],
                 "rank_complete": ez["rank_complete"], "shift": ez["rank_complete"] - ez["rank_imputed"]})
    rows.sort(key=lambda m: m["rank_complete"])

    W, rh, mt, ml = 700, 30, 58, 150
    H = mt + rh * len(rows) + 40
    rmax = max(max(m["rank_imputed"], m["rank_complete"]) for m in rows) + 12
    pw = W - ml - 20

    def X(rank): return ml + (rank / rmax) * pw

    s = [_t(ml, 16, "ComfyUI: what complete review data changed", 12.5, INK, weight=600),
         f'<circle cx="{ml+6}" cy="30" r="4.2" fill="{PAPER}" stroke="{INK3}" stroke-width="1.6"/>',
         _t(ml + 16, 34, "rank with review data estimated", 10.5, INK2),
         f'<circle cx="{ml+226}" cy="30" r="4.2" fill="{ESPRESSO}"/>',
         _t(ml + 236, 34, "rank with complete review data", 10.5, INK2)]
    for gv in (1, 50, 100, 150, 200, 250):
        if gv > rmax:
            continue
        x = X(gv)
        s.append(f'<line x1="{x:.1f}" y1="{mt-8}" x2="{x:.1f}" y2="{H-30}" stroke="{GRID}"/>')
        s.append(_t(x, H - 16, f"#{gv}", 10, INK3, anchor="middle", mono=True))
    for i, m in enumerate(rows):
        y = mt + i * rh + rh / 2
        hot = m["name"] == "enzymezoo-code"
        x1, x2 = X(m["rank_imputed"]), X(m["rank_complete"])
        s.append(_t(ml - 10, y, m["name"], 11, INK if hot else INK2, anchor="end",
                    weight=600 if hot else 400, dy=3.5))
        s.append(f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" stroke="{HAIR2}" stroke-width="1.5"/>')
        s.append(f'<circle cx="{x1:.1f}" cy="{y:.1f}" r="4.2" fill="{PAPER}" '
                 f'stroke="{RUST if hot else INK3}" stroke-width="1.6">'
                 f'<title>{esc(m["name"])}: #{m["rank_imputed"]} estimated</title></circle>')
        s.append(f'<circle cx="{x2:.1f}" cy="{y:.1f}" r="4.2" fill="{RUST if hot else ESPRESSO}">'
                 f'<title>{esc(m["name"])}: #{m["rank_complete"]} complete</title></circle>')
        if hot:
            s.append(_t(max(x1, x2) + 10, y, f"one commit · #{m['rank_imputed']} estimated, "
                        f"#{m['rank_complete']} measured", 10.5, INK, dy=3.5, weight=600))
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Rank under estimated versus complete review data">{"".join(s)}</svg>'


def fig_slope(fv, cu, n):
    rows = fv["authors"]
    by_commits = sorted(rows, key=lambda r: (-r["commits"], r["rank"]))
    crank = {r["name"]: i + 1 for i, r in enumerate(by_commits)}
    names = ({r["name"] for r in by_commits[:12]}
             | {r["name"] for r in sorted(rows, key=lambda r: r["rank"])[:12]})
    ents = sorted(names, key=lambda x: crank[x])
    hi = {"alexzms": RUST, "Satyam Srivastava": RUST, "Zhang Peiyuan": BLUE}

    W, mt, ph = 700, 56, 380
    H = mt + ph + 30
    xl, xr = 235, 465
    rmax = max(max(crank[x] for x in ents),
               max(r["rank"] for r in rows if r["name"] in ents)) + 1

    def Y(rank): return mt + (rank / rmax) * ph

    s = [_t(350, 16, "FastVideo: rank by commit count vs rank by impact", 12.5, INK,
            anchor="middle", weight=600),
         _t(xl, 40, "by commits", 11, INK2, anchor="end", weight=600),
         _t(xr, 40, "by impact", 11, INK2, weight=600)]
    used_l, used_r = [], []

    def place(used, y):
        while any(abs(y - u) < 13 for u in used):
            y += 13
        used.append(y)
        return y

    for name in ents:
        r = next(x for x in rows if x["name"] == name)
        y1, y2 = Y(crank[name]), Y(r["rank"])
        col, wgt = hi.get(name, HAIR2), 2.2 if name in hi else 1.4
        s.append(f'<line x1="{xl+8}" y1="{y1:.1f}" x2="{xr-8}" y2="{y2:.1f}" stroke="{col}" stroke-width="{wgt}">'
                 f'<title>{esc(name)}: #{crank[name]} by commits, #{r["rank"]} by impact</title></line>')
        ly, ry = place(used_l, y1), place(used_r, y2)
        ink = INK if name in hi else INK2
        w = 600 if name in hi else 400
        s.append(_t(xl, ly, f"{name}  #{crank[name]}", 10.5, ink, anchor="end", dy=3.5, weight=w))
        s.append(_t(xr, ry, f"#{r['rank']}  {name}", 10.5, ink, dy=3.5, weight=w))
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Rank by commit count versus rank by impact, FastVideo">{"".join(s)}</svg>'


# Draft figure number -> (builder, caption template). Captions may reference
# numbers.json via .format(n=numbers).
FIGURES = {
    1: (fig_scatters,
        "Figure 1. Each dot is a contributor, placed by commit count (log scale) and impact "
        "score. The two panels share both axes. On FastVideo the cloud climbs with commit "
        "count; on ComfyUI it barely does."),
    2: (fig_slope,
        "Figure 2. The same people ranked two ways on FastVideo. Lines that fall from left "
        "to right mark contributors whose impact rank is better than their commit-count rank."),
    3: (fig_lorenz,
        "Figure 3. Cumulative share of surviving code, largest owners first. The dashed line "
        "is perfect equality. The marked point is where each curve crosses half the codebase."),
    4: (fig_dumbbell,
        "Figure 4. What complete review data changed on ComfyUI. Hollow dots show each "
        "contributor's rank while review data was estimated; filled dots show the rank once "
        "the fetch completed. The snapshots are a few days apart, so a small part of the "
        "movement is ordinary weekly drift."),
}


# ---------------------------------------------------------------- numbers guard
GUARD_WHITELIST = {
    # citation year and time-of-day in prose
    "1979", "2",
    # scale glosses: correlation endpoints, the epsilon example, the weights
    "0", "1.0", "0.25", "0.0005",
    # approximate public facts stated as approximations
    "120,000",
    # "top 6%" derived from #19 of 311
    "6",
}


def _number_variants(v) -> set[str]:
    out = set()
    if isinstance(v, bool) or v is None:
        return out
    if isinstance(v, int):
        out |= {str(v), f"{v:,}"}
    elif isinstance(v, float):
        out |= {f"{v:g}", f"{v:.2f}", f"{v:.1f}", str(round(v * 100)), f"{round(v):,}"}
    return out


def allowed_numbers(numbers: dict) -> set[str]:
    allowed = set(GUARD_WHITELIST)

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        else:
            allowed.update(_number_variants(x))
    walk(numbers)
    return allowed


def guard_numbers(html_text: str, numbers: dict) -> list[str]:
    """Every numeric token in the essay prose must trace to numbers.json or the
    whitelist. Figure SVGs check their own sources; captions are prose."""
    prose = re.sub(r"<(svg|style|script|head).*?</\1>", " ", html_text, flags=re.S)
    prose = re.sub(r"<[^>]+>", " ", prose)
    tokens = set(re.findall(r"\d[\d,]*(?:\.\d+)?", prose))
    allowed = allowed_numbers(numbers)
    for v in numbers.get("_provenance", {}).values():
        if isinstance(v, str):
            allowed.update(re.findall(r"\d+", v))
    return sorted(tok for tok in tokens if tok.rstrip(".") not in allowed
                  and tok.replace(",", "") not in allowed)


# -------------------------------------------------------------------- assembly
def extract_site_css() -> str:
    css = SITE_CSS.read_text()
    root_start = css.index(":root {")
    root_block = css[root_start: css.index("}", root_start) + 1]
    fonts_match = re.search(r"/\* -{10,} fonts", css)
    if not fonts_match:
        sys.exit("build_essay: fonts banner not found in styles.css")
    return root_block + "\n" + css[fonts_match.start():]


def inject(template: str, marker: str, value: str) -> str:
    token = f"<!--@INJECT:{marker}-->"
    if token not in template:
        sys.exit(f"build_essay: marker {token} missing from template")
    return template.replace(token, value)


def render_body(body, notes, fv, cu, numbers) -> str:
    note_by_idx: dict[int, list[dict]] = {}
    paragraphs = [(i, b) for i, (kind, b) in enumerate(body) if kind == "p"]
    for note in notes:
        hits = [i for i, text in paragraphs if note["anchor"] in text]
        if len(hits) != 1:
            sys.exit(f"build_essay: sidenote anchor {note['anchor']!r} matched {len(hits)} paragraphs")
        note_by_idx.setdefault(hits[0], []).append(note)

    out = []
    for i, (kind, b) in enumerate(body):
        if kind == "p":
            notes_here = note_by_idx.get(i, [])
            if notes_here:
                inner = "".join(f'<div class="mn-item"><p class="mn-label">{esc(x["label"])}</p>'
                                f'<p>{esc(x["text"])}</p></div>' for x in notes_here)
                out.append(f'<aside class="mn">{inner}</aside>')
            out.append(f"<p>{render_inline(b)}</p>")
        elif kind == "h2":
            out.append(f"<h2>{render_inline(b)}</h2>")
        elif kind == "hr":
            out.append("<hr>")
        elif kind == "ul":
            items = "".join(f"<li>{render_inline(item)}</li>" for item in b)
            out.append(f"<ul>{items}</ul>")
        elif kind == "pair":
            cols = "".join(f"<div><p>{render_inline(p)}</p></div>" for p in b)
            out.append(f'<div class="pair">{cols}</div>')
        elif kind == "figure":
            builder, caption = FIGURES[b]
            out.append(f'<figure class="figure">{builder(fv, cu, numbers)}'
                       f"<figcaption>{esc(caption)}</figcaption></figure>")
    return "\n".join(out)


def og_card_html(title: str, dek: str, numbers: dict, css_tokens: str) -> str:
    fv, cu = numbers["fastvideo"], numbers["comfyui"]
    stats = (f"contributors {fv['meta']['n_authors']} / {cu['meta']['n_authors']}"
             f"&nbsp;&nbsp;·&nbsp;&nbsp;rank correlation {fv['meta']['rho']:.2f} / {cu['meta']['rho']:.2f}"
             f"&nbsp;&nbsp;·&nbsp;&nbsp;hold half the code: "
             f"{WORDS.get(fv['hold_half'], fv['hold_half'])} people / "
             f"{WORDS.get(cu['hold_half'], cu['hold_half'])} person")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{css_tokens}
* {{ margin:0; box-sizing:border-box; }}
body {{ width:1200px; height:630px; background:var(--paper); color:var(--ink);
       font-family:var(--ui); display:flex; align-items:center; }}
.card {{ padding:0 96px; }}
.k {{ font-family:var(--mono); font-size:20px; letter-spacing:.14em; text-transform:uppercase;
      color:var(--ink-3); margin-bottom:28px; }}
h1 {{ font-family:var(--display); font-weight:600; font-size:88px; letter-spacing:-.025em;
      line-height:1.04; margin-bottom:24px; }}
.d {{ font-size:30px; color:var(--ink-2); max-width:900px; line-height:1.4; margin-bottom:44px; }}
.s {{ font-family:var(--mono); font-size:21px; color:var(--verm-deep);
      border-top:1px solid var(--hair-2); padding-top:24px; }}
</style></head><body><div class="card">
<p class="k">One engine · two repositories</p>
<h1>{esc(title)}</h1>
<p class="d">{esc(dek)}</p>
<p class="s">{stats}</p>
</div></body></html>"""


def render_og(og_html: str, out_png: Path) -> None:
    from playwright.sync_api import sync_playwright
    tmp = out_png.with_suffix(".og.html")
    tmp.write_text(og_html)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630})
        page.goto(tmp.as_uri())
        page.wait_for_timeout(250)
        page.screenshot(path=str(out_png), clip={"x": 0, "y": 0, "width": 1200, "height": 630})
        browser.close()
    tmp.unlink()


def build_html(numbers: dict, frozen: bool) -> tuple[str, str, str]:
    """Assemble the full page. Returns (html, title, dek); exits on any
    truthfulness violation (markers, external subresources, untraced numbers)."""
    fv = load_payload(ROOT / "docs" / "index.html")
    cu = load_payload(ROOT / "docs" / "comfyui" / "index.html")
    freeze_date = numbers["_provenance"]["comfyui_payload"].split(" ")[0]

    title, dek, stamp, body = parse_draft(DRAFT.read_text(), frozen, freeze_date)
    body_html = render_body(body, sidenotes(numbers), fv, cu, numbers)

    site_url = os.environ.get("SITE_URL", DEFAULT_URL).rstrip("/") + "/"
    engine = tool_repo_url()
    footer = (f'numbers as of {esc(freeze_date)} · '
              f'<a href="{esc(fv["meta"]["repo_url"])}">FastVideo repo</a> · '
              f'<a href="../">FastVideo dashboard</a> · '
              f'<a href="../comfyui/">ComfyUI dashboard</a> · '
              f'<a href="../methodology.md">methodology</a>'
              + (f' · <a href="{esc(engine)}">run it on your repo ↗</a>' if engine else ""))

    css = extract_site_css() + "\n" + ESSAY_CSS.read_text()
    html = TEMPLATE.read_text()
    for marker, value in [("TITLE", esc(title)), ("DESC", esc(dek)), ("DEK", esc(dek)),
                          ("STAMP", esc(stamp)), ("URL", esc(site_url)),
                          ("OGIMAGE", esc(site_url + "og.png")), ("CSS", css),
                          ("BODY", body_html), ("FOOTER", footer)]:
        html = inject(html, marker, value)
    if "<!--@INJECT:" in html:
        sys.exit("build_essay: unresolved INJECT marker left in output")

    ext = re.findall(r'<(?:img|script|link)[^>]+(?:src|href)="https?://[^"]*"', html)
    if ext:
        sys.exit(f"build_essay: external subresource found: {ext[:2]}")

    unknown = guard_numbers(html, numbers)
    if unknown:
        sys.exit(f"build_essay: numbers not traceable to numbers.json: {unknown}")
    return html, title, dek


def main() -> None:
    numbers = json.loads(NUMBERS.read_text())
    frozen = bool(numbers["_provenance"].get("FROZEN"))
    out_root = ROOT / ("docs" if frozen else "dist") / SLUG
    if "--docs" in sys.argv and not frozen:
        sys.exit("build_essay: numbers.json is not frozen; refusing to write docs/")

    html, title, dek = build_html(numbers, frozen)
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "index.html").write_text(html)
    print(f"wrote {out_root / 'index.html'} ({len(html) // 1024} KB, "
          f"{'FROZEN' if frozen else 'PREVIEW'})")

    if "--skip-og" not in sys.argv:
        render_og(og_card_html(title, dek, numbers, extract_site_css()), out_root / "og.png")
        print(f"wrote {out_root / 'og.png'}")


if __name__ == "__main__":
    main()
