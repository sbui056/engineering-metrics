"""End-to-end tests for the validation harness on synthetic six-table sets.

The point of these tests is that validate uses the PRODUCERS' predicates and
schema constants — so a rule the producers enforce (bot filtering, exclusions)
fails validation when violated, including cases the old hand-copied marker
lists were blind to (web-flow, __pycache__).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from merge_and_score import build_scored  # noqa: E402
from narrate import build_rationales  # noqa: E402
from validate import run_checks  # noqa: E402


def _tables():
    """A minimal, fully consistent six-table set that must PASS every check."""
    commits = pd.DataFrame({
        "commit_hash": ["h1", "h2", "h3"],
        "author_canonical": ["Alice", "Bob", "Alice"],
        "author_email_raw": ["a@x.z", "b@x.z", "a@x.z"],
        "date": pd.to_datetime(["2025-01-01", "2025-06-01", "2026-01-01"], utc=True),
        "file_path": ["core/a.py", "core/b.py", "core/a.py"],
        "additions": [10, 5, 3],
        "deletions": [0, 1, 2],
        "is_merge": [False, False, False],
    })
    ownership_file = pd.DataFrame({
        "file_path": ["core/a.py", "core/b.py"],
        "author_canonical": ["Alice", "Bob"],
        "blame_lines": [10, 8],
        "blame_share": [1.0, 1.0],
        "is_blame_leader": [True, True],
        "is_major_owner": [True, True],
        "top_owner_proportion": [1.0, 1.0],
        "minor_contributor_count": [0, 0],
        "is_orphan_risk": [True, True],
    })
    ownership_author = pd.DataFrame({
        "author_canonical": ["Alice", "Bob"],
        "ownership_concentration": [900.0, 100.0],
        "code_survival_tenure_normalized": [0.9, np.nan],
        "bus_factor_flag": [True, True],
    })
    coupling = pd.DataFrame({
        "file_path": ["core/a.py", "core/b.py"],
        "centrality_score": [0.6, 0.4],
        "weighted_degree": [1.0, 1.0],
    })
    reviews = pd.DataFrame({
        "author_canonical": ["Alice"],
        "reviewer_login": ["alice"],
        "review_count": [4],
        "distinct_authors_reviewed": [2],
        "approval_rate": [0.75],
        "status": ["complete"],
    }).astype({"review_count": "int64", "distinct_authors_reviewed": "int64"})
    scored, _ = build_scored(commits, ownership_author, ownership_file, coupling, reviews)
    scored["one_line_rationale"] = build_rationales(scored)
    return {
        "commits_clean": commits,
        "reviews": reviews,
        "coupling": coupling,
        "ownership_file": ownership_file,
        "ownership_author": ownership_author,
        "scored": scored,
    }


def test_consistent_tables_pass(capsys):
    checker = run_checks(_tables())
    out = capsys.readouterr().out
    assert checker.failures == 0, out


def test_bot_author_fails_via_real_predicate(capsys):
    t = _tables()
    bot = t["commits_clean"].iloc[[0]].assign(
        author_canonical="GitHub", author_email_raw="noreply@web-flow.github.com"
    )
    # web-flow was invisible to the old hand-copied BOT_MARKERS list.
    t["commits_clean"] = pd.concat([t["commits_clean"], bot], ignore_index=True)
    checker = run_checks(t)
    out = capsys.readouterr().out
    assert "[FAIL] no bot authors slipped through (is_bot)" in out
    assert checker.failures >= 1


def test_excluded_path_fails_via_real_predicate(capsys):
    t = _tables()
    bad = t["commits_clean"].iloc[[0]].assign(file_path="core/__pycache__/a.pyc")
    # __pycache__ was invisible to the old EXCLUDED_MARKERS substrings.
    t["commits_clean"] = pd.concat([t["commits_clean"], bad], ignore_index=True)
    checker = run_checks(t)
    out = capsys.readouterr().out
    assert "[FAIL] no excluded/vendored paths (is_excluded)" in out
    assert checker.failures >= 1


def test_lockfile_lookalike_does_not_false_fail(capsys):
    # src/foo.lock.ts is NOT excluded by the producer (exact-name lockfile
    # match only); the old '.lock' substring check would have false-FAILed it.
    t = _tables()
    ok = t["commits_clean"].iloc[[0]].assign(file_path="src/foo.lock.ts")
    t["commits_clean"] = pd.concat([t["commits_clean"], ok], ignore_index=True)
    # Keep the scored universe consistent (same author, so no mismatch).
    checker = run_checks(t)
    out = capsys.readouterr().out
    assert "[FAIL] no excluded/vendored paths" not in out, out
