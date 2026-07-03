"""Unit tests for the merge/score step (pure functions on small frames)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from merge_and_score import (  # noqa: E402
    SCORED_COLUMNS, assign_tiers, build_scored, owned_criticality, pct_rank,
    review_leverage_raw, shown_metrics, top_level_dir,
)


def _commits(rows):
    df = pd.DataFrame(rows, columns=["author_canonical", "date", "file_path", "is_merge"])
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df["commit_hash"] = [f"h{i}" for i in range(len(df))]
    df["additions"] = 1
    df["deletions"] = 0
    df["author_email_raw"] = "x@y.z"
    return df


def test_pct_rank_preserves_nan_and_handles_ties():
    s = pd.Series([0.0, 0.0, 5.0, np.nan])
    p = pct_rank(s)
    assert p[2] == 1.0
    assert p[0] == p[1] < p[2]
    assert np.isnan(p[3])


def test_owned_criticality_weights_centrality_by_blame_share():
    ownership_file = pd.DataFrame({
        "file_path": ["a.py", "a.py", "b.py"],
        "author_canonical": ["Alice", "Bob", "Alice"],
        "blame_share": [0.8, 0.2, 1.0],
    })
    coupling = pd.DataFrame({
        "file_path": ["a.py", "b.py", "orphan.py"],
        "centrality_score": [0.5, 0.1, 0.9],
    })
    crit = owned_criticality(coupling, ownership_file)
    assert crit["Alice"] == 0.8 * 0.5 + 1.0 * 0.1
    assert crit["Bob"] == 0.2 * 0.5
    assert "orphan.py" not in crit.index  # unblamed files contribute to nobody


def test_review_leverage_formula():
    reviews = pd.DataFrame({
        "author_canonical": ["Alice"],
        "reviewer_login": ["alice"],
        "review_count": [7],
        "distinct_authors_reviewed": [3],
        "approval_rate": [0.5],
        "status": ["complete"],
    })
    lev = review_leverage_raw(reviews)
    assert lev["Alice"] == 3 * np.log1p(7)
    assert review_leverage_raw(reviews.iloc[0:0]).empty


def test_assign_tiers_groups_within_epsilon():
    # Gaps: 0.001, 0.049, 0.05, 0.05 -> median ~0.0495, eps ~0.0247: only the
    # unusually tight 0.001 pair is indistinguishable and shares a tier.
    scores = pd.Series([0.90, 0.899, 0.85, 0.80, 0.75], index=list("abcde"))
    tiers = assign_tiers(scores)
    assert list(tiers) == [1, 1, 2, 3, 4]
    # Exact ties always share a tier regardless of epsilon.
    tied = assign_tiers(pd.Series([0.9, 0.9, 0.5], index=list("xyz")))
    assert list(tied) == [1, 1, 2]
    assert list(assign_tiers(pd.Series([0.5]))) == [1]


def test_shown_metrics_breadth_recency_consistency():
    commits = _commits([
        # Alice: 3 files across 2 dirs + root, active weeks 1 and 3 of a 3-week span.
        ("Alice", "2026-01-05", "src/a.py", False),
        ("Alice", "2026-01-06", "docs/readme.md", False),
        ("Alice", "2026-01-19", "setup.py", False),
        # Bob: single commit, older; merge rows must be ignored.
        ("Bob", "2026-01-01", "src/b.py", False),
        ("Bob", "2026-01-26", "src/merge.py", True),
    ])
    m = shown_metrics(commits).set_index("author_canonical")
    alice = m.loc["Alice"]
    assert alice["breadth_files"] == 3
    assert alice["breadth_dirs"] == 3  # src, docs, (root)
    assert alice["recency_days"] == 0  # window end = Alice's last non-merge commit
    assert alice["consistency"] == 2 / 3
    bob = m.loc["Bob"]
    assert bob["breadth_files"] == 1  # the merge row didn't count
    assert bob["recency_days"] == 18
    assert bob["consistency"] == 1.0
    assert top_level_dir("deep/nested/f.py") == "deep"
    assert top_level_dir("root.py") == "(root)"


def _small_inputs(review_status="complete"):
    commits = _commits([
        ("Alice", "2025-01-01", "core/a.py", False),
        ("Bob", "2025-06-01", "core/b.py", False),
        ("Cara", "2026-01-01", "docs/c.md", False),
    ])
    ownership_author = pd.DataFrame({
        "author_canonical": ["Alice", "Bob"],
        "ownership_concentration": [900.0, 100.0],
        "code_survival_tenure_normalized": [0.9, np.nan],  # Bob too new to judge
        "bus_factor_flag": [True, False],
    })
    ownership_file = pd.DataFrame({
        "file_path": ["core/a.py", "core/b.py"],
        "author_canonical": ["Alice", "Bob"],
        "blame_share": [1.0, 1.0],
    })
    coupling = pd.DataFrame({
        "file_path": ["core/a.py", "core/b.py"],
        "centrality_score": [0.6, 0.2],
    })
    reviews = pd.DataFrame({
        "author_canonical": ["Alice", "Zoe"],  # Zoe reviews but never committed
        "reviewer_login": ["alice", "zoe"],
        "review_count": [10, 2],
        "distinct_authors_reviewed": [2, 1],
        "approval_rate": [0.8, 1.0],
        "status": [review_status] * 2,
    })
    return commits, ownership_author, ownership_file, coupling, reviews


def test_build_scored_schema_and_ordering():
    df, diag = build_scored(*_small_inputs())
    assert list(df.columns) == SCORED_COLUMNS
    assert diag["n_authors"] == 3
    assert list(df["author_canonical"]) == sorted(
        df["author_canonical"], key=lambda a: -df.set_index("author_canonical")
        .loc[a, "impact_score"]
    )
    assert df.iloc[0]["author_canonical"] == "Alice"  # leads every signal
    assert (df["impact_score"] <= 1.0).all() and (df["impact_score"] > 0).all()
    assert diag["pure_reviewers_excluded"] == ["Zoe"]
    assert df["one_line_rationale"].eq("").all()


def test_build_scored_complete_reviews_mean_true_zeros():
    df, diag = build_scored(*_small_inputs("complete"))
    assert diag["review_complete"]
    assert df["has_review_data"].all()
    assert not df["review_data_imputed"].any()
    row = df.set_index("author_canonical")
    # Bob and Cara gave zero reviews: bottom of the review percentile, tied.
    assert row.loc["Bob", "review_leverage"] == row.loc["Cara", "review_leverage"]
    assert row.loc["Alice", "review_leverage"] == 1.0
    # Bob's NaN survival was median-imputed.
    assert diag["n_survival_imputed"] >= 1
    assert row.loc["Bob", "code_survival_tenure_normalized"] == 0.5


def test_build_scored_partial_reviews_are_imputed():
    df, _ = build_scored(*_small_inputs("partial"))
    row = df.set_index("author_canonical")
    assert bool(row.loc["Alice", "has_review_data"])
    assert not bool(row.loc["Bob", "has_review_data"])
    assert bool(row.loc["Bob", "review_data_imputed"])
    assert row.loc["Bob", "review_leverage"] == 0.5
    assert not bool(row.loc["Alice", "review_data_imputed"])
