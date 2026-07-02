"""Unit tests for the coupling-graph helpers (synthetic data, no files needed)."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from compute_coupling import build_pairs, commit_file_sets, prune_pairs, score_files  # noqa: E402


def _sets(*groups):
    return [frozenset(g) for g in groups]


def test_inverse_size_weighting():
    # One commit touching 3 files: each pair gets 1/(3-1) = 0.5.
    pw, ps, fc, n = build_pairs(_sets({"a", "b", "c"}))
    assert n == 1
    assert pw[("a", "b")] == pw[("a", "c")] == pw[("b", "c")] == 0.5
    assert ps[("a", "b")] == 1


def test_size_cap_drops_large_commits():
    big = {f"f{i}" for i in range(25)}
    pw, ps, fc, n = build_pairs(_sets(big, {"a", "b"}), max_commit_files=20)
    assert n == 1  # only the small commit is considered
    assert ("a", "b") in pw
    assert all("f0" not in pair for pair in pw)


def test_single_file_commits_count_toward_lift_but_make_no_pairs():
    pw, ps, fc, n = build_pairs(_sets({"a"}, {"a", "b"}))
    assert n == 2
    assert fc["a"] == 2 and fc["b"] == 1
    assert ps[("a", "b")] == 1


def test_prune_requires_min_support():
    file_sets = _sets({"a", "b"}, {"c", "d"}, {"c", "d"})
    pw, ps, fc, n = build_pairs(file_sets)
    kept = prune_pairs(pw, ps, fc, n, min_support=2, min_lift=1.0)
    assert ("c", "d") in kept and ("a", "b") not in kept


def test_prune_requires_lift_above_chance():
    # "x" appears in every commit, so P(x & y) == P(x)P(y)*... compute:
    # x in 4/4 commits, y in 2/4, pair in 2 -> lift = (2*4)/(4*2) = 1.0, not > 1.
    file_sets = _sets({"x", "y"}, {"x", "y"}, {"x", "z"}, {"x", "w"})
    pw, ps, fc, n = build_pairs(file_sets)
    kept = prune_pairs(pw, ps, fc, n, min_support=2, min_lift=1.0)
    assert ("x", "y") not in kept


def test_score_files_covers_isolated_files():
    edges = {("a", "b"): 1.0}
    df = score_files(edges, {"a", "b", "lonely.py"})
    assert set(df.columns) == {"file_path", "centrality_score", "weighted_degree"}
    lonely = df[df.file_path == "lonely.py"].iloc[0]
    assert lonely.centrality_score == 0.0 and lonely.weighted_degree == 0.0
    assert (df[df.file_path != "lonely.py"].centrality_score > 0).all()


def test_commit_file_sets_collapses_coauthor_rows_and_merges():
    df = pd.DataFrame({
        "commit_hash": ["c1", "c1", "c1", "c2"],
        "file_path": ["a", "a", "b", "z"],   # a listed twice (two co-authors)
        "is_merge": [False, False, False, True],
    })
    fs = commit_file_sets(df)
    assert fs["c1"] == frozenset({"a", "b"})
    assert "c2" not in fs.index  # merge excluded
