"""Extract every number the essay states into numbers.json.

Sources (deliberately, per plan):
- Live deployed payloads (docs/index.html, docs/comfyui/index.html): the only
  numbers allowed into essay prose. Re-run after the freeze dispatch.
- data-comfyui/scored.parquet (2026-07-11, status=complete): the "complete"
  side of the F3 imputed<->complete rank-shift figure.
- The imputed side of F3 defaults to the live ComfyUI payload while it is
  still partial; after the freeze it must come from git b25a3f8.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "drafts" / "numbers.json"

PAYLOAD_RE = re.compile(r"window\.__DATA__\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S)


def load_payload_html(html: str) -> dict:
    return json.loads(PAYLOAD_RE.search(html).group(1))


def load_payload(path: Path) -> dict:
    return load_payload_html(path.read_text())


def zero_review(r):
    return r["review"] is None or r["review"].get("count", 0) == 0


def summarize(d: dict) -> dict:
    rows = d["authors"]
    curve = d["org"]["curve"]
    hold_half = next(i + 1 for i, v in enumerate(curve) if v >= 0.5)
    by_rank = sorted(rows, key=lambda r: r["rank"])
    one_commit = [r for r in rows if r["commits"] == 1]
    oc_ranks = sorted(r["rank"] for r in one_commit) or [0]
    return {
        "one_commit": {
            "count": len(one_commit),
            # by commit count, every one-commit contributor shares this rank
            "tie_rank": sum(1 for r in rows if r["commits"] >= 2) + 1,
            "best_rank": oc_ranks[0],
            "worst_rank": oc_ranks[-1],
        },
        "meta": {k: d["meta"][k] for k in (
            "n_authors", "n_commits", "n_files", "n_tiers", "rho",
            "window_label", "review_status", "generated_at", "repo", "repo_url")},
        "gini": d["org"]["gini"],
        "median_second": d["org"]["median_second"],
        "top1_share": round(curve[0], 4),
        "hold_half": hold_half,
        "top10_share": round(curve[9], 4),
        "zero_review_count": sum(1 for r in rows if zero_review(r)),
        "review_imputed_count": sum(1 for r in rows if r["flags"].get("review_imputed")),
        "reviewer_count": sum(1 for r in rows if not zero_review(r)),
        "top5": [
            {"name": r["name"], "rank": r["rank"], "tier": r["tier"],
             "impact": round(r["impact"], 4), "commits": r["commits"]}
            for r in by_rank[:5]
        ],
    }


def person(d: dict, name: str) -> dict | None:
    r = next((r for r in d["authors"] if r["name"] == name), None)
    if r is None:
        return None
    out = {k: r[k] for k in ("name", "rank", "tier", "commits")}
    out["impact"] = round(r["impact"], 4)
    out["review"] = r["review"]
    out["review_imputed"] = r["flags"].get("review_imputed", False)
    out["signals"] = r.get("signals")
    out["owned"] = r.get("owned")
    return out


def risk_entry(d: dict, name: str) -> dict | None:
    e = d["org"]["risk"].get(name)
    if e is None:
        return None
    return {"sole_files": e["files"], "cen_share": e["cen_share"],
            "no_second": e["no_second"], "nearest": e["nearest"]}


def complete_comfyui_ranks() -> dict:
    """Ranks from the 2026-07-11 complete-reviews analysis (local parquet)."""
    df = pd.read_parquet(ROOT / "data-comfyui" / "scored.parquet")
    df = df.sort_values("impact_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    return {
        "n": len(df),
        "imputed_count": int(df["review_data_imputed"].sum()),
        "ranks": dict(zip(df["author_canonical"], df["rank"].astype(int))),
        "impact": {a: round(float(s), 4) for a, s in zip(df["author_canonical"], df["impact_score"])},
    }


def f3_movers(imputed_payload: dict, complete: dict, top_n: int = 12) -> list[dict]:
    """Largest rank shifts between the imputed and complete ComfyUI states."""
    imp_ranks = {r["name"]: r["rank"] for r in imputed_payload["authors"]}
    imp_flag = {r["name"]: r["flags"].get("review_imputed", False)
                for r in imputed_payload["authors"]}
    movers = []
    for name, comp_rank in complete["ranks"].items():
        if name in imp_ranks:
            movers.append({
                "name": name,
                "rank_imputed": imp_ranks[name],
                "rank_complete": comp_rank,
                "shift": comp_rank - imp_ranks[name],
                "was_imputed": imp_flag[name],
            })
    movers.sort(key=lambda m: -abs(m["shift"]))
    return movers[:top_n]


def main():
    fv = load_payload(ROOT / "docs" / "index.html")
    cu = load_payload(ROOT / "docs" / "comfyui" / "index.html")

    # Imputed-state ComfyUI payload: live page while partial; b25a3f8 after freeze.
    if cu["meta"]["review_status"] == "partial":
        cu_imputed = cu
        imputed_source = "live payload (still partial)"
    else:
        html = subprocess.run(
            ["git", "-C", str(ROOT), "show", "b25a3f8:docs/comfyui/index.html"],
            capture_output=True, text=True, check=True).stdout
        cu_imputed = load_payload_html(html)
        imputed_source = "git b25a3f8"

    complete = complete_comfyui_ranks()

    numbers = {
        "_provenance": {
            "fastvideo_payload": fv["meta"]["generated_at"],
            "comfyui_payload": cu["meta"]["generated_at"],
            "comfyui_review_status": cu["meta"]["review_status"],
            "f3_imputed_source": imputed_source,
            "f3_complete_source": "data-comfyui/scored.parquet (2026-07-11, complete)",
            "FROZEN": cu["meta"]["review_status"] == "complete",
        },
        "fastvideo": summarize(fv),
        "comfyui": summarize(cu),
        "people": {
            "fastvideo": {n: person(fv, n) for n in (
                "alexzms", "William Lin", "Zhang Peiyuan", "Satyam Srivastava",
                "Yongqi Chen", "Wenxuan Tan", "Shao Duan", "Jinzhe Pan")},
            "comfyui": {n: person(cu, n) for n in (
                "comfyanonymous", "guill", "enzymezoo-code", "Alexander Piskun")},
        },
        "risk": {
            "fastvideo": {"William Lin": risk_entry(fv, "William Lin")},
            "comfyui": {"comfyanonymous": risk_entry(cu, "comfyanonymous")},
        },
        "f3": {
            "movers": f3_movers(cu_imputed, complete),
            "enzymezoo": {
                "rank_imputed": next(r["rank"] for r in cu_imputed["authors"]
                                     if r["name"] == "enzymezoo-code"),
                "rank_complete": complete["ranks"].get("enzymezoo-code"),
                "n": complete["n"],
            },
            "complete_imputed_count": complete["imputed_count"],
        },
    }

    OUT.write_text(json.dumps(numbers, indent=2))
    print(f"wrote {OUT}")
    print(json.dumps(numbers["_provenance"], indent=2))
    print("\nF3 enzymezoo:", numbers["f3"]["enzymezoo"])
    print("\nF3 top movers:")
    for m in numbers["f3"]["movers"]:
        tag = " (imputed)" if m["was_imputed"] else ""
        print(f"  {m['name']}: {m['rank_imputed']} -> {m['rank_complete']} ({m['shift']:+d}){tag}")


if __name__ == "__main__":
    sys.exit(main())
