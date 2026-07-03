"""Unit tests for the ownership/survival helpers (synthetic data, no git needed)."""
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from compute_ownership import (  # noqa: E402
    HALF_LIFE_YEARS, RECENT_DAYS, build_author_table, build_file_table, parse_porcelain,
)

NOW = pd.Timestamp("2026-07-01", tz="UTC")


def test_parse_porcelain_extracts_author_and_time():
    text = (
        "abc123 1 1 1\n"
        "author Alice Smith\n"
        "author-mail <alice@a.com>\n"
        "author-time 1700000000\n"
        "author-tz +0000\n"
        "filename f.py\n"
        "\tdef foo():\n"
        "abc123 2 2\n"
        "author Alice Smith\n"
        "author-mail <alice@a.com>\n"
        "author-time 1700000000\n"
        "\t    return 1\n"
    )
    meta = parse_porcelain(text)
    assert meta == [("Alice Smith", "alice@a.com", 1700000000)] * 2


def _file_df(counts, commits_to_file=None):
    return build_file_table(counts, commits_to_file or {})


def test_major_owner_requires_share_and_floor():
    # Bob has 4% share -> never major. Carol has 10% but 1 commit and 10 lines -> floored out.
    counts = {"f.py": Counter({"Alice": 86, "Carol": 10, "Bob": 4})}
    df = _file_df(counts, {("f.py", "Alice"): 5, ("f.py", "Carol"): 1, ("f.py", "Bob"): 1})
    by = df.set_index("author_canonical")
    assert by.loc["Alice", "is_major_owner"]
    assert not by.loc["Carol", "is_major_owner"]   # share ok, floor not met
    assert not by.loc["Bob", "is_major_owner"]     # share below 5%
    assert by.loc["Alice", "is_blame_leader"]
    assert (df["top_owner_proportion"] == 0.86).all()
    assert (df["minor_contributor_count"] == 1).all()  # only Bob is <5%


def test_line_floor_substitutes_for_commit_floor():
    # Dave has 30 surviving lines (>= 25) with only 1 commit -> still major.
    counts = {"g.py": Counter({"Dave": 30, "Erin": 70})}
    df = _file_df(counts, {("g.py", "Dave"): 1, ("g.py", "Erin"): 9})
    assert df.set_index("author_canonical").loc["Dave", "is_major_owner"]


def test_orphan_risk_is_single_major_owner():
    one = _file_df({"a.py": Counter({"Alice": 100})}, {("a.py", "Alice"): 3})
    two = _file_df(
        {"b.py": Counter({"Alice": 50, "Bob": 50})},
        {("b.py", "Alice"): 3, ("b.py", "Bob"): 3},
    )
    assert one["is_orphan_risk"].all()
    assert not two["is_orphan_risk"].any()


def _author_table(file_counts, commits_to_file, surviving_old, added_rows):
    file_df = _file_df(file_counts, commits_to_file)
    added = pd.DataFrame(added_rows, columns=["author_canonical", "date", "additions"])
    added["date"] = pd.to_datetime(added["date"], utc=True)
    return build_author_table(file_df, Counter(surviving_old), added, NOW)


def test_survival_clamped_and_recent_excluded():
    # Alice added 100 lines 2y ago and 1000 lines yesterday; 80 old lines survive.
    # Denominator must be the old 100 only -> rate 0.8 (not 80/1100), then
    # decay-normalized upward for age.
    tbl = _author_table(
        {"f.py": Counter({"Alice": 80})},
        {("f.py", "Alice"): 5},
        {"Alice": 80},
        [("Alice", NOW - pd.Timedelta(days=730), 100),
         ("Alice", NOW - pd.Timedelta(days=1), 1000)],
    )
    s = tbl.set_index("author_canonical").loc["Alice", "code_survival_tenure_normalized"]
    expected_baseline = 0.5 ** ((730 / 365.25) / HALF_LIFE_YEARS)
    assert abs(s - 0.8 / expected_baseline) < 1e-9


def test_survival_nan_when_all_additions_recent():
    tbl = _author_table(
        {"f.py": Counter({"Newbie": 50})},
        {("f.py", "Newbie"): 2},
        {},
        [("Newbie", NOW - pd.Timedelta(days=RECENT_DAYS - 10), 50)],
    )
    assert pd.isna(
        tbl.set_index("author_canonical").loc["Newbie", "code_survival_tenure_normalized"]
    )


def test_concentration_is_size_weighted_owned_share():
    # Alice major-owns big.py (910 lines, ~99%) and small.py (10 lines, 100%):
    # concentration = (900/910)*910 + 1.0*10 = 910. Bob (10 lines, 1 commit)
    # clears neither floor, so he owns nothing majorly.
    counts = {
        "big.py": Counter({"Alice": 900, "Bob": 10}),
        "small.py": Counter({"Alice": 10}),
    }
    c2f = {("big.py", "Alice"): 5, ("big.py", "Bob"): 1, ("small.py", "Alice"): 3}
    tbl = _author_table(counts, c2f, {}, [])
    by = tbl.set_index("author_canonical")
    assert abs(by.loc["Alice", "ownership_concentration"] - 910.0) < 1e-9
    assert by.loc["Bob", "ownership_concentration"] == 0.0


def test_bus_factor_flag():
    counts = {"a.py": Counter({"Alice": 100}), "b.py": Counter({"Alice": 50, "Bob": 50})}
    c2f = {("a.py", "Alice"): 3, ("b.py", "Alice"): 3, ("b.py", "Bob"): 3}
    tbl = _author_table(counts, c2f, {}, []).set_index("author_canonical")
    assert tbl.loc["Alice", "bus_factor_flag"]      # sole major owner of a.py
    assert not tbl.loc["Bob", "bus_factor_flag"]    # b.py has two major owners
