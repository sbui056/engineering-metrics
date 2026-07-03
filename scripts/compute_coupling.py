"""Build the co-change coupling graph and score file criticality.

Reads data/commits_clean.parquet, builds a weighted file-pair graph from
non-merge commits (inverse-size edge weights, size-capped commits, edges pruned
by lift and support), and scores each file with PageRank. Output is file-grain:
data/coupling.parquet (file_path, centrality_score, weighted_degree).

The author-level roll-up is intentionally not done here; the merge step joins
this table to per-file blame shares.

Usage: python scripts/compute_coupling.py
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import networkx as nx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

COUPLING_COLUMNS = ["file_path", "centrality_score", "weighted_degree"]

MAX_COMMIT_FILES = 20   # commits touching more than this many files are dropped
MIN_SUPPORT = 2         # a pair must co-change in at least this many commits
MIN_LIFT = 1.0          # and more often than chance


def commit_file_sets(df: pd.DataFrame) -> pd.Series:
    """Distinct file sets per non-merge commit (collapses co-author row splits)."""
    non_merge = df[~df["is_merge"]]
    return non_merge.groupby("commit_hash")["file_path"].agg(lambda s: frozenset(s))


def build_pairs(
    file_sets: list[frozenset],
    max_commit_files: int = MAX_COMMIT_FILES,
) -> tuple[Counter, Counter, Counter, int]:
    """Accumulate pair weights and supports over size-capped multi-file commits.

    Returns (pair_weight, pair_support, file_commits, n_considered):
      - pair_weight[(a, b)]: total 1/(n-1) weight, keys sorted
      - pair_support[(a, b)]: number of commits the pair co-changed in
      - file_commits[f]: number of considered commits touching f
      - n_considered: commits that passed the size cap (denominator for lift)
    """
    pair_weight: Counter = Counter()
    pair_support: Counter = Counter()
    file_commits: Counter = Counter()
    n_considered = 0
    for files in file_sets:
        if len(files) > max_commit_files:
            continue
        n_considered += 1
        for f in files:
            file_commits[f] += 1
        n = len(files)
        if n < 2:
            continue
        w = 1.0 / (n - 1)
        for a, b in combinations(sorted(files), 2):
            pair_weight[(a, b)] += w
            pair_support[(a, b)] += 1
    return pair_weight, pair_support, file_commits, n_considered


def prune_pairs(
    pair_weight: Counter,
    pair_support: Counter,
    file_commits: Counter,
    n_considered: int,
    min_support: int = MIN_SUPPORT,
    min_lift: float = MIN_LIFT,
) -> dict:
    """Keep pairs with support >= min_support and lift > min_lift."""
    kept = {}
    for pair, w in pair_weight.items():
        s = pair_support[pair]
        if s < min_support:
            continue
        a, b = pair
        lift = (s * n_considered) / (file_commits[a] * file_commits[b])
        if lift > min_lift:
            kept[pair] = w
    return kept


def score_files(edges: dict, all_files: set) -> pd.DataFrame:
    g = nx.Graph()
    for (a, b), w in edges.items():
        g.add_edge(a, b, weight=w)
    pagerank = nx.pagerank(g, weight="weight") if g.number_of_edges() else {}
    degree = dict(g.degree(weight="weight")) if g.number_of_nodes() else {}
    rows = [
        {
            "file_path": f,
            "centrality_score": pagerank.get(f, 0.0),
            "weighted_degree": degree.get(f, 0.0),
        }
        for f in sorted(all_files)
    ]
    return pd.DataFrame(rows, columns=COUPLING_COLUMNS)


def main() -> None:
    ap = argparse.ArgumentParser(description="Compute co-change file criticality.")
    ap.add_argument("--max-commit-files", type=int, default=MAX_COMMIT_FILES)
    args = ap.parse_args()
    config.ensure_dirs()

    df = pd.read_parquet(config.DATA_DIR / "commits_clean.parquet")
    file_sets = commit_file_sets(df)
    sizes = file_sets.map(len)

    print("Commit-size distribution (files touched per non-merge commit):")
    for q in (0.5, 0.75, 0.9, 0.95, 0.99, 1.0):
        print(f"  p{int(q * 100):<3} {sizes.quantile(q):>8.0f}")
    dropped = int((sizes > args.max_commit_files).sum())
    print(f"  commits dropped by size cap (> {args.max_commit_files} files): "
          f"{dropped} of {len(sizes)}")

    pair_weight, pair_support, file_commits, n_considered = build_pairs(
        list(file_sets), args.max_commit_files
    )
    edges = prune_pairs(pair_weight, pair_support, file_commits, n_considered)
    all_files = set(df["file_path"].unique())
    out_df = score_files(edges, all_files)

    out = config.DATA_DIR / "coupling.parquet"
    out_df.to_parquet(out, index=False)

    connected = int((out_df["centrality_score"] > 0).sum())
    print(f"\nWrote {out}  ({len(out_df):,} files, {len(edges):,} edges kept of "
          f"{len(pair_weight):,} raw pairs, {connected:,} files with nonzero centrality)")
    print("\nTop 10 by centrality:")
    top = out_df.nlargest(10, "centrality_score")
    for _, r in top.iterrows():
        print(f"  {r.centrality_score:.5f}  {r.file_path}")


if __name__ == "__main__":
    main()
