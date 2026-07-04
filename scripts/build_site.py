"""Build the static dashboard site: data/*.parquet -> dist/index.html.

Reads the same five tables the Streamlit app binds to, precomputes everything
the page needs (percentiles, commit counts, symlog positions, weekly activity,
per-author owned-file evidence), and inlines the JSON payload plus CSS/JS from
site/src/ into one self-contained HTML file — no external requests, works from
file://. The browser only renders; every number is computed here.

Run: python scripts/build_site.py   (after `make narrate`, which fills
one_line_rationale in scored.parquet in place)
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
sys.path.insert(0, str(Path(__file__).resolve().parent))
from identity import noreply_login

SITE_SRC = config.ROOT / "site" / "src"
DIST = config.ROOT / "dist"

FRAMES = ["scored", "commits_clean", "reviews", "ownership_file", "coupling"]

# Contributor-field geometry: one plot rect shared by every view; the browser
# reads it from the payload instead of duplicating constants.
FIELD_W, FIELD_H = 920, 500
FIELD_M = {"l": 56, "r": 20, "t": 18, "b": 44}
FIELD_R = 4.5  # dot radius in viewBox units

SIGNAL_COLUMNS = [
    ("ownership_concentration", "Ownership concentration", "Own"),
    ("code_survival_tenure_normalized", "Code survival (tenure-norm.)", "Surv"),
    ("coupling_criticality", "Coupling criticality (owned)", "Coup"),
    ("review_leverage", "Review leverage", "Rev"),
]

X_TICK_VALUES = [1, 3, 10, 30, 100, 300]
TOP_FILES_N = 10
SCATTER_LABELS_N = 3  # each side, same as dashboard.py


def load_frames() -> dict[str, pd.DataFrame]:
    frames = {}
    for name in FRAMES:
        path = config.DATA_DIR / f"{name}.parquet"
        if not path.exists():
            sys.exit(f"Missing {path}. Run `make all` first.")
        frames[name] = pd.read_parquet(path)
    return frames


def beeswarm_layout(
    x: np.ndarray, pw: float, ph: float, r: float = FIELD_R, gap: float = 1.0
) -> np.ndarray:
    """Deterministic 1D beeswarm: normalized [0,1] x in, (n, 2) normalized out.

    Exact-tie groups (the true-zero review block is 59 authors) would stack
    into a needle taller than the plot, so ties are dithered into multiple
    columns first (bounded x displacement), then a standard sweep packs dots
    upward/downward from the axis center. No RNG anywhere.
    """
    n = len(x)
    px = np.asarray(x, dtype=float) * pw
    pitch = 2 * r + gap
    max_rows = max(int((ph * 0.9) // pitch), 1)

    # 1) split exact ties across columns, center-out
    keys = np.round(np.asarray(x, dtype=float), 4)
    dithered = px.copy()
    for key in np.unique(keys):
        idx = np.flatnonzero(keys == key)
        k = len(idx)
        if k <= max_rows:
            continue
        cols = int(np.ceil(k / max_rows))
        for pos, i in enumerate(idx):
            col = pos % cols
            dithered[i] += (col - (cols - 1) / 2) * pitch

    # 2) sweep: place in dithered-x order, choosing the y closest to the axis
    order = sorted(range(n), key=lambda i: (dithered[i], i))
    ys = np.zeros(n)
    placed: list[int] = []
    for i in order:
        neighbors = [j for j in placed if abs(dithered[j] - dithered[i]) < pitch]
        candidates = [0.0]
        for j in neighbors:
            dy = np.sqrt(max(pitch**2 - (dithered[j] - dithered[i]) ** 2, 0.0))
            candidates.extend([ys[j] + dy, ys[j] - dy])
        candidates.sort(key=abs)
        for y in candidates:
            if all(
                (dithered[j] - dithered[i]) ** 2 + (ys[j] - y) ** 2 >= pitch**2 - 1e-9
                for j in neighbors
            ):
                ys[i] = y
                break
        placed.append(i)

    out = np.column_stack([dithered / pw, 0.5 + ys / ph])
    return np.clip(out, 0.0, 1.0)


def tier_layout(
    tiers: np.ndarray, pw: float, ph: float, r: float = FIELD_R, gap: float = 2.5
) -> np.ndarray:
    """Tier columns: x by tier index, dots stacked up from the baseline by rank."""
    tiers = np.asarray(tiers, dtype=int)
    n_tiers = int(tiers.max())
    pitch = 2 * r + gap
    xs = np.zeros(len(tiers))
    ys = np.zeros(len(tiers))
    for t in np.unique(tiers):
        idx = np.flatnonzero(tiers == t)  # scored is rank-sorted, so stack by rank
        xs[idx] = (t - 0.5) / n_tiers
        for pos, i in enumerate(idx):
            ys[i] = 1.0 - (pos + 0.5) * pitch / ph
    return np.column_stack([xs, ys])


def github_logins(commits: pd.DataFrame, reviews: pd.DataFrame) -> dict[str, str]:
    """Confirmed GitHub login per author — noreply emails first, then the
    reviewer bridge. Never guessed from display names: no evidence, no link."""
    logins: dict[str, str] = {}
    for author, grp in commits.groupby("author_canonical"):
        found = {noreply_login(e) for e in grp["author_email_raw"]} - {None}
        if len(found) == 1:
            logins[author] = found.pop()
        elif len(found) > 1:
            print(f"  ambiguous noreply logins for {author}: {sorted(found)} — skipping")
    for r in reviews.itertuples():
        logins.setdefault(r.author_canonical, r.reviewer_login)
    return logins


def commit_counts(commits: pd.DataFrame) -> pd.Series:
    """Non-merge distinct commits per author — same as the Streamlit contrast chart."""
    return (
        commits[~commits["is_merge"]]
        .groupby("author_canonical")["commit_hash"]
        .nunique()
    )


def weekly_activity(commits: pd.DataFrame) -> tuple[dict[str, list[int]], int]:
    """Distinct non-merge commits per author per week, on one shared week grid."""
    nm = commits[~commits["is_merge"]]
    dates = nm["date"].dt.tz_convert("UTC").dt.normalize()
    week_start = dates - pd.to_timedelta(dates.dt.dayofweek, unit="D")
    origin = week_start.min()
    week_idx = ((week_start - origin).dt.days // 7).astype(int)
    n_weeks = int(week_idx.max()) + 1
    per = (
        nm.assign(week=week_idx.values)
        .groupby(["author_canonical", "week"])["commit_hash"]
        .nunique()
    )
    out: dict[str, list[int]] = {}
    for author, series in per.groupby(level=0):
        arr = np.zeros(n_weeks, dtype=int)
        weeks = series.index.get_level_values("week").to_numpy()
        arr[weeks] = series.to_numpy()
        out[author] = arr.tolist()
    return out, n_weeks


def top_owned_files(
    ownership_file: pd.DataFrame, coupling: pd.DataFrame, author: str, n: int = TOP_FILES_N
) -> list[dict]:
    """The evidence table in the drill-down — same join as the Streamlit app."""
    owned = (
        ownership_file[ownership_file["author_canonical"] == author]
        .merge(coupling[["file_path", "centrality_score"]], on="file_path", how="left")
        .fillna({"centrality_score": 0.0})
        .sort_values("centrality_score", ascending=False)
        .head(n)
    )
    return [
        {
            "path": r.file_path,
            "blame_share": round(float(r.blame_share), 4),
            "centrality": round(float(r.centrality_score), 6),
            "orphan": bool(r.is_orphan_risk),
        }
        for r in owned.itertuples()
    ]


def scatter_labels(scored: pd.DataFrame, counts: pd.Series, n: int = SCATTER_LABELS_N) -> list[str]:
    """Label only the divergent cases — the rank-gap rule from the Streamlit chart."""
    d = scored.merge(
        counts.rename("commit_count").reset_index(), on="author_canonical", how="left"
    ).fillna({"commit_count": 0})
    d = d.assign(
        rank_gap=d["commit_count"].rank(ascending=False)
        - d["impact_score"].rank(ascending=False)
    )
    label_set = pd.concat([d.nlargest(n, "rank_gap"), d.nsmallest(n, "rank_gap")])
    return label_set["author_canonical"].tolist()


def build_payload(frames: dict[str, pd.DataFrame]) -> dict:
    scored = frames["scored"]
    commits = frames["commits_clean"]
    reviews = frames["reviews"]
    ownership_file = frames["ownership_file"]
    coupling = frames["coupling"]

    # The leaderboard is rank-ordered; keep the file's tie order but make the
    # ordering explicit rather than assumed.
    scored = scored.sort_values("impact_score", ascending=False, kind="stable").reset_index(
        drop=True
    )

    counts = commit_counts(commits)
    weekly, n_weeks = weekly_activity(commits)
    reviews_by_author = {r.author_canonical: r for r in reviews.itertuples()}
    logins = github_logins(commits, reviews)

    # Contributor-field layouts, one position per author per view, all
    # precomputed here so the browser only interpolates between them.
    pw = FIELD_W - FIELD_M["l"] - FIELD_M["r"]
    ph = FIELD_H - FIELD_M["t"] - FIELD_M["b"]
    author_commits = scored["author_canonical"].map(counts).fillna(0).astype(int)
    sx_arr = np.log1p(author_commits.to_numpy(dtype=float))
    sx_max = round(float(np.log1p(max(counts.max(), X_TICK_VALUES[-1]))) * 1.04, 4)
    impact_arr = scored["impact_score"].to_numpy(dtype=float)
    layouts = {"spectrum": beeswarm_layout(impact_arr, pw, ph)}
    for key, _, _ in SIGNAL_COLUMNS:
        layouts[key] = beeswarm_layout(scored[key].to_numpy(dtype=float), pw, ph)
    layouts["activity"] = np.column_stack([sx_arr / sx_max, 1.0 - impact_arr])
    layouts["tiers"] = tier_layout(scored["tier"].to_numpy(), pw, ph)
    view_names = {
        "ownership_concentration": "own",
        "code_survival_tenure_normalized": "surv",
        "coupling_criticality": "coup",
        "review_leverage": "rev",
    }

    window_start = commits["date"].min()
    window_end = commits["date"].max()
    review_status = (
        "complete"
        if (not reviews.empty and (reviews["status"] == "complete").all())
        else "partial"
    )

    authors = []
    for i, row in scored.iterrows():
        name = row["author_canonical"]
        n_commits = int(counts.get(name, 0))
        rev = reviews_by_author.get(name)
        authors.append(
            {
                "name": name,
                "rank": i + 1,
                "tier": int(row["tier"]),
                "impact": round(float(row["impact_score"]), 4),
                "signals": {
                    key: round(float(row[key]), 4) for key, _, _ in SIGNAL_COLUMNS
                },
                "flags": {
                    "bus_factor": bool(row["bus_factor_flag"]),
                    "review_imputed": bool(row["review_data_imputed"]),
                },
                "rationale": str(row["one_line_rationale"]),
                "aux": {
                    "breadth_files": int(row["breadth_files"]),
                    "breadth_dirs": int(row["breadth_dirs"]),
                    "recency_days": int(row["recency_days"]),
                    "consistency": round(float(row["consistency"]), 3),
                },
                "review": (
                    {
                        "count": int(rev.review_count),
                        "distinct_authors": int(rev.distinct_authors_reviewed),
                        "approval_rate": round(float(rev.approval_rate), 3),
                    }
                    if rev is not None
                    else None
                ),
                "top_files": top_owned_files(ownership_file, coupling, name),
                "commits": n_commits,
                "sx": round(float(np.log1p(n_commits)), 4),
                "weekly": weekly.get(name, [0] * n_weeks),
                "github": logins.get(name),
                "views": {
                    view_names.get(k, k): [round(float(v[0]), 4), round(float(v[1]), 4)]
                    for k, v in (
                        [("spectrum", layouts["spectrum"][i]),
                         ("activity", layouts["activity"][i]),
                         ("tiers", layouts["tiers"][i])]
                        + [(key, layouts[key][i]) for key, _, _ in SIGNAL_COLUMNS]
                    )
                },
            }
        )

    tier_counts = scored["tier"].value_counts()
    tiers = [
        {"tier": t, "count": int(tier_counts.get(t, 0))}
        for t in range(1, int(scored["tier"].max()) + 1)
    ]

    tier_sizes = {t["tier"]: t["count"] for t in tiers}
    biggest_tier = max(tier_sizes, key=tier_sizes.get)
    n_tiers = int(scored["tier"].max())
    tick_tiers = sorted(
        {1, n_tiers, biggest_tier} | {t for t in (10, 20, 30, 40) if t <= n_tiers}
    )
    return {
        "meta": {
            "repo": config.get_repo_path().name,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "window_start": str(window_start.date()),
            "window_end": str(window_end.date()),
            "window_label": f"{window_start.strftime('%b %Y')} → {window_end.strftime('%b %Y')}",
            "review_status": review_status,
            "n_authors": len(scored),
            "n_tiers": int(scored["tier"].max()),
            "n_commits": int(commits.loc[~commits["is_merge"], "commit_hash"].nunique()),
            "n_files": int(ownership_file["file_path"].nunique()),
        },
        "signals": [
            {"key": key, "label": label, "short": short}
            for key, label, short in SIGNAL_COLUMNS
        ],
        "authors": authors,
        "field": {
            "w": FIELD_W, "h": FIELD_H, "m": FIELD_M, "r": FIELD_R,
            "x_ticks": [
                {"v": v, "x": round(float(np.log1p(v)) / sx_max, 4)}
                for v in X_TICK_VALUES
            ],
            "labeled": scatter_labels(scored, counts),
            "tier_ticks": [
                {"t": t, "x": round((t - 0.5) / n_tiers, 4)} for t in tick_tiers
            ],
        },
        "tiers": tiers,
    }


def render_html(payload: dict) -> str:
    template = (SITE_SRC / "template.html").read_text(encoding="utf-8")
    css = (SITE_SRC / "styles.css").read_text(encoding="utf-8")
    js = (SITE_SRC / "app.js").read_text(encoding="utf-8")

    # </ would close the inline <script> if a path or rationale ever contained it.
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")

    meta = payload["meta"]
    eyebrow = (
        f"<strong>{html.escape(meta['repo'])}</strong> · "
        f"{html.escape(meta['window_label'])} · "
        f"{meta['n_commits']:,} non-merge commits · "
        f"{meta['n_files']:,} files at HEAD"
    )
    footer = (
        f"Generated {html.escape(meta['generated_at'])} · "
        f"window {html.escape(meta['window_start'])} → {html.escape(meta['window_end'])} · "
        f"review fetch {html.escape(meta['review_status'])}"
    )

    out = template
    for marker, value in [
        ("<!--@INJECT:CSS-->", css),
        ("<!--@INJECT:JS-->", js),
        ("<!--@INJECT:DATA-->", data),
        ("<!--@INJECT:EYEBROW-->", eyebrow),
        ("<!--@INJECT:FOOTER-->", footer),
    ]:
        if marker not in out:
            sys.exit(f"template.html is missing marker {marker}")
        out = out.replace(marker, value)
    return out


def main() -> None:
    frames = load_frames()
    payload = build_payload(frames)
    page = render_html(payload)
    DIST.mkdir(parents=True, exist_ok=True)
    out_path = DIST / "index.html"
    out_path.write_text(page, encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(
        f"Wrote {out_path} ({size_kb:.0f} KB) — "
        f"{payload['meta']['n_authors']} authors, {payload['meta']['n_tiers']} tiers"
    )


if __name__ == "__main__":
    main()
