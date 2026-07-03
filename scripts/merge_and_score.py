"""Merge the four signals into data/scored.parquet — applied once, here, not per track.

impact_score = 0.25 * pct(ownership_concentration)
             + 0.25 * pct(code_survival_tenure_normalized)
             + 0.25 * pct(coupling_criticality)
             + 0.25 * pct(review_leverage)

Each component is percentile-of-rank normalized (never z-scores: repo activity
is heavy-tailed and ranks are already robust to outliers). Equal weights are a
deliberate, transparent choice, not a calibrated one.

coupling_criticality is owned-criticality, computed here: coupling.parquet
joined to ownership_file.parquet on file_path, each file's centrality_score
weighted by the author's blame_share, summed per author. It measures the
criticality of what an author owns, not raw activity.

review_leverage = distinct_authors_reviewed * log1p(review_count).

Missing-signal policy (median, never zero, so a data gap can't read as "worst"):
  - reviews: if the fetch was complete, an author absent from reviews.parquet
    genuinely gave zero reviews — that's a true zero, scored as such, and
    has_review_data stays true (coverage exists). Only when the fetch was
    partial (or the table is empty) does absence become unknowable:
    has_review_data=false, review_leverage imputed to the 50th percentile,
    review_data_imputed=true.
  - survival: authors whose additions are all inside the recency window have
    NaN survival (no basis yet) and are likewise imputed to the median.

Uncertainty via tiers, not a bootstrap: contributors whose scores sit within
an epsilon (~half the median adjacent-score gap) of their neighbor share a
tier, so within-tier order isn't overclaimed at small N.

The leaderboard universe is authors with at least one commit in commits_clean.
Pure reviewers (review activity, zero commits) are excluded and reported: with
three of four signals undefined, a rank would be mostly imputation.

Shown-not-scored (computed here from non-merge commits, displayed only):
breadth_files, breadth_dirs, recency_days (vs the data-window end, not wall
clock, so output is a function of data only), consistency (active weeks over
the author's own first-to-last-commit span).

Usage: python scripts/merge_and_score.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

TIER_EPS_FACTOR = 0.5  # epsilon = this fraction of the median adjacent-score gap

SCORED_COLUMNS = [
    "author_canonical", "impact_score", "ownership_concentration",
    "code_survival_tenure_normalized", "coupling_criticality", "review_leverage",
    "has_review_data", "review_data_imputed", "bus_factor_flag", "tier",
    "breadth_files", "breadth_dirs", "recency_days", "consistency",
    "one_line_rationale",
]


def pct_rank(s: pd.Series) -> pd.Series:
    """Percentile-of-rank in (0, 1]; NaNs stay NaN (imputed by the caller)."""
    return s.rank(pct=True, method="average")


def owned_criticality(coupling: pd.DataFrame, ownership_file: pd.DataFrame) -> pd.Series:
    """Sum of centrality_score * blame_share per author (criticality of what they own)."""
    j = ownership_file[["file_path", "author_canonical", "blame_share"]].merge(
        coupling[["file_path", "centrality_score"]], on="file_path", how="inner"
    )
    j["owned"] = j["centrality_score"] * j["blame_share"]
    return j.groupby("author_canonical")["owned"].sum()


def review_leverage_raw(reviews: pd.DataFrame) -> pd.Series:
    """distinct_authors_reviewed * log1p(review_count), indexed by author."""
    if reviews.empty:
        return pd.Series(dtype="float64")
    r = reviews.set_index("author_canonical")
    return r["distinct_authors_reviewed"] * np.log1p(r["review_count"])


def assign_tiers(scores: pd.Series, eps_factor: float = TIER_EPS_FACTOR) -> pd.Series:
    """Tier numbers (1 = top) for a Series of impact scores.

    Sorted descending, a new tier starts when the drop to the previous
    contributor exceeds epsilon = eps_factor * median adjacent gap. Scores
    within epsilon of their neighbor chain into the same tier.
    """
    s = scores.sort_values(ascending=False)
    if len(s) <= 1:
        return pd.Series(1, index=s.index, dtype="int64")
    gaps = -s.diff().dropna()
    eps = eps_factor * float(gaps.median())
    tiers, tier = [1], 1
    for gap in gaps:
        if gap > eps:
            tier += 1
        tiers.append(tier)
    return pd.Series(tiers, index=s.index, dtype="int64").reindex(scores.index)


def top_level_dir(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else "(root)"


def shown_metrics(commits: pd.DataFrame, window_end: pd.Timestamp | None = None) -> pd.DataFrame:
    """breadth_files / breadth_dirs / recency_days / consistency per author.

    Non-merge commits only (the shared merge convention). recency_days is
    measured against the data-window end (max commit date), not wall clock.
    consistency = active weeks / weeks in the author's own first-to-last span,
    so it measures cadence while active; departure shows up in recency_days.
    """
    c = commits[~commits["is_merge"]].copy()
    if window_end is None:
        window_end = c["date"].max()
    c["dir"] = c["file_path"].map(top_level_dir)
    c["week"] = c["date"].dt.tz_convert("UTC").dt.tz_localize(None).dt.to_period("W")

    g = c.groupby("author_canonical")
    first_week = g["week"].min()
    last_week = g["week"].max()
    span_weeks = (last_week.astype("int64") - first_week.astype("int64")) + 1
    out = pd.DataFrame({
        "breadth_files": g["file_path"].nunique(),
        "breadth_dirs": g["dir"].nunique(),
        "recency_days": (window_end - g["date"].max()).dt.days,
        "consistency": g["week"].nunique() / span_weeks,
    })
    return out.astype({
        "breadth_files": "int64", "breadth_dirs": "int64", "recency_days": "int64",
        "consistency": "float64",
    }).reset_index()


def build_scored(
    commits: pd.DataFrame,
    ownership_author: pd.DataFrame,
    ownership_file: pd.DataFrame,
    coupling: pd.DataFrame,
    reviews: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """Assemble scored.parquet's table; returns (df, diagnostics)."""
    universe = sorted(commits.loc[~commits["is_merge"], "author_canonical"].unique())
    df = pd.DataFrame({"author_canonical": universe})

    df = df.merge(ownership_author, on="author_canonical", how="left")
    df["ownership_concentration"] = df["ownership_concentration"].fillna(0.0)
    df["bus_factor_flag"] = df["bus_factor_flag"].astype("boolean").fillna(False).astype(bool)

    crit = owned_criticality(coupling, ownership_file)
    df["coupling_criticality_raw"] = (
        df["author_canonical"].map(crit).fillna(0.0)
    )

    leverage = review_leverage_raw(reviews)
    review_complete = (not reviews.empty) and (reviews["status"] == "complete").all()
    df["review_leverage_raw"] = df["author_canonical"].map(leverage)
    if review_complete:
        # Coverage is total: absence means zero reviews given, a true zero.
        df["has_review_data"] = True
        df["review_leverage_raw"] = df["review_leverage_raw"].fillna(0.0)
    else:
        df["has_review_data"] = df["review_leverage_raw"].notna()

    # Percentile-normalize each signal over the universe; impute gaps at median.
    df["ownership_concentration"] = pct_rank(df["ownership_concentration"])
    survival_pct = pct_rank(df["code_survival_tenure_normalized"])
    n_survival_imputed = int(survival_pct.isna().sum())
    df["code_survival_tenure_normalized"] = survival_pct.fillna(0.5)
    df["coupling_criticality"] = pct_rank(df["coupling_criticality_raw"])
    review_pct = pct_rank(df["review_leverage_raw"])
    df["review_data_imputed"] = review_pct.isna()
    df["review_leverage"] = review_pct.fillna(0.5)

    df["impact_score"] = 0.25 * (
        df["ownership_concentration"]
        + df["code_survival_tenure_normalized"]
        + df["coupling_criticality"]
        + df["review_leverage"]
    )
    df["tier"] = assign_tiers(df["impact_score"])
    df = df.merge(shown_metrics(commits), on="author_canonical", how="left")
    df["one_line_rationale"] = ""

    df = (
        df[SCORED_COLUMNS]
        .sort_values(["impact_score", "author_canonical"], ascending=[False, True])
        .reset_index(drop=True)
    )

    # Diagnostics for the printout — join coverage and imputation counts.
    active_files = set(coupling.loc[coupling["centrality_score"] > 0, "file_path"])
    blamed_files = set(ownership_file["file_path"])
    pure_reviewers = (
        sorted(set(reviews["author_canonical"]) - set(universe))
        if not reviews.empty else []
    )
    diag = {
        "n_authors": len(df),
        "review_complete": review_complete,
        "n_review_imputed": int(df["review_data_imputed"].sum()),
        "n_survival_imputed": n_survival_imputed,
        "coupling_files_unmatched": len(active_files - blamed_files),
        "coupling_files_active": len(active_files),
        "pure_reviewers_excluded": pure_reviewers,
        "n_tiers": int(df["tier"].max()) if len(df) else 0,
    }
    return df, diag


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge signals into data/scored.parquet.")
    ap.parse_args()
    config.ensure_dirs()

    commits = pd.read_parquet(config.DATA_DIR / "commits_clean.parquet")
    ownership_author = pd.read_parquet(config.DATA_DIR / "ownership_author.parquet")
    ownership_file = pd.read_parquet(config.DATA_DIR / "ownership_file.parquet")
    coupling = pd.read_parquet(config.DATA_DIR / "coupling.parquet")
    reviews = pd.read_parquet(config.DATA_DIR / "reviews.parquet")

    df, diag = build_scored(commits, ownership_author, ownership_file, coupling, reviews)
    out = config.DATA_DIR / "scored.parquet"
    df.to_parquet(out, index=False)

    print(f"Wrote {out}  ({diag['n_authors']} authors, {diag['n_tiers']} tiers)")
    print(f"  review data:               "
          f"{'complete' if diag['review_complete'] else 'PARTIAL'} "
          f"({diag['n_review_imputed']} authors median-imputed)")
    print(f"  survival median-imputed:   {diag['n_survival_imputed']} authors "
          f"(all additions too recent)")
    print(f"  coupling files with centrality but no blame rows: "
          f"{diag['coupling_files_unmatched']} / {diag['coupling_files_active']}")
    if diag["pure_reviewers_excluded"]:
        print(f"  pure reviewers excluded (no commits): "
              f"{', '.join(diag['pure_reviewers_excluded'])}")

    print("\nTop 15 by impact score:")
    cols = ["tier", "impact_score", "ownership_concentration",
            "code_survival_tenure_normalized", "coupling_criticality",
            "review_leverage", "bus_factor_flag"]
    top = df.head(15).set_index("author_canonical")[cols]
    print(top.to_string(float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main()
