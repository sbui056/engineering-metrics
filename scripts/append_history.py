"""Append one snapshot row per author to the committed history ledger.

Every scheduled refresh is a longitudinal observation — but only if recorded.
This writes docs/data/history-<slug>.csv (append-only; rerunning on the same
date replaces that date's rows instead of duplicating them), giving future
trajectory features months of data for free.

Interpretation caveat (documented here because it binds every consumer):
scores are percentile-normalized within each snapshot's population — a rank
drop can mean others rose or joined, not that someone's work decayed.

Usage: DATA_DIR=data-comfyui python scripts/append_history.py --slug comfyui
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

LEDGER_COLUMNS = [
    "run_date", "author", "rank", "tier", "impact",
    "own", "surv", "coup", "rev", "commits", "has_review_data",
]


def snapshot(scored: pd.DataFrame, commits: pd.DataFrame, run_date: str) -> pd.DataFrame:
    sc = scored.sort_values("impact_score", ascending=False, kind="stable").reset_index(drop=True)
    counts = (
        commits.loc[~commits["is_merge"]]
        .groupby("author_canonical")["commit_hash"].nunique()
    )
    return pd.DataFrame({
        "run_date": run_date,
        "author": sc["author_canonical"],
        "rank": sc.index + 1,
        "tier": sc["tier"].astype(int),
        "impact": sc["impact_score"].round(4),
        "own": sc["ownership_concentration"].round(4),
        "surv": sc["code_survival_tenure_normalized"].round(4),
        "coup": sc["coupling_criticality"].round(4),
        "rev": sc["review_leverage"].round(4),
        "commits": sc["author_canonical"].map(counts).fillna(0).astype(int),
        "has_review_data": sc["has_review_data"].astype(bool),
    })[LEDGER_COLUMNS]


def append(ledger_path: Path, snap: pd.DataFrame) -> pd.DataFrame:
    """Append-only with same-date replacement (idempotent reruns)."""
    if ledger_path.exists():
        prior = pd.read_csv(ledger_path, dtype={"run_date": str})
        run_date = snap["run_date"].iloc[0]
        prior = prior[prior["run_date"] != run_date]
        out = pd.concat([prior, snap], ignore_index=True)
    else:
        out = snap
    return out.sort_values(["run_date", "rank"], kind="stable").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True,
                    help="deployment slug; ledger lands at docs/data/history-<slug>.csv")
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    scored = pd.read_parquet(config.DATA_DIR / "scored.parquet")
    commits = pd.read_parquet(config.DATA_DIR / "commits_clean.parquet")
    snap = snapshot(scored, commits, args.date)

    ledger_path = config.ROOT / "docs" / "data" / f"history-{args.slug}.csv"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    out = append(ledger_path, snap)
    out.to_csv(ledger_path, index=False)
    print(f"Wrote {ledger_path} ({len(out)} rows, "
          f"{out['run_date'].nunique()} snapshot(s), latest {args.date})")


if __name__ == "__main__":
    main()
