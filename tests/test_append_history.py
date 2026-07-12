"""Ledger invariants: schema, append-only, same-date idempotence."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from append_history import LEDGER_COLUMNS, append, snapshot  # noqa: E402


def _scored():
    return pd.DataFrame({
        "author_canonical": ["Alice", "Bob"],
        "impact_score": [0.9, 0.5],
        "tier": [1, 2],
        "ownership_concentration": [1.0, 0.5],
        "code_survival_tenure_normalized": [0.9, 0.4],
        "coupling_criticality": [0.8, 0.6],
        "review_leverage": [0.95, 0.5],
        "has_review_data": [True, False],
    })


def _commits():
    return pd.DataFrame({
        "commit_hash": ["a1", "a2", "b1", "m1"],
        "author_canonical": ["Alice", "Alice", "Bob", "Bob"],
        "is_merge": [False, False, False, True],
    })


def test_snapshot_schema_and_ranks():
    snap = snapshot(_scored(), _commits(), "2026-07-11")
    assert list(snap.columns) == LEDGER_COLUMNS
    assert snap["rank"].tolist() == [1, 2]
    assert snap["author"].tolist() == ["Alice", "Bob"]
    assert snap["commits"].tolist() == [2, 1]  # merges excluded


def test_append_accumulates_and_same_date_replaces(tmp_path):
    ledger = tmp_path / "history-x.csv"
    day1 = snapshot(_scored(), _commits(), "2026-07-11")
    out1 = append(ledger, day1)
    out1.to_csv(ledger, index=False)
    # second run same day: replaces, never duplicates
    out1b = append(ledger, day1)
    assert len(out1b) == 2
    # a later day accumulates
    day2 = snapshot(_scored(), _commits(), "2026-07-18")
    out1b.to_csv(ledger, index=False)
    out2 = append(ledger, day2)
    assert len(out2) == 4
    assert out2["run_date"].nunique() == 2
    # append-only: day1 rows survive untouched
    assert (out2[out2["run_date"] == "2026-07-11"]["impact"] == [0.9, 0.5]).all()
