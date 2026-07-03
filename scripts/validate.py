"""Validation harness: check every data/ table against the contract in CLAUDE.md.

Runs schema checks (exact column names, in order) and cross-file invariants:
blame shares sum to 1 per file, exactly one blame leader per file, PageRank
mass sums to ~1, the scoring identity holds, imputation flags are coherent,
and the scored universe matches the commit authors. Prints one PASS/FAIL line
per check and exits nonzero if anything failed — wire into `make validate`.

Schemas and filter rules are IMPORTED from their producers (single source of
truth), so this harness tests the real predicates rather than a copy that can
silently drift.

Usage: python scripts/validate.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from compute_coupling import COUPLING_COLUMNS  # noqa: E402
from compute_ownership import OWNERSHIP_AUTHOR_COLUMNS, OWNERSHIP_FILE_COLUMNS  # noqa: E402
from extract_commits import COMMITS_COLUMNS, is_bot, is_excluded  # noqa: E402
from fetch_reviews import REVIEWS_COLUMNS  # noqa: E402
from merge_and_score import SCORED_COLUMNS  # noqa: E402

SCHEMAS = {
    "commits_clean": COMMITS_COLUMNS,
    "reviews": REVIEWS_COLUMNS,
    "coupling": COUPLING_COLUMNS,
    "ownership_file": OWNERSHIP_FILE_COLUMNS,
    "ownership_author": OWNERSHIP_AUTHOR_COLUMNS,
    "scored": SCORED_COLUMNS,
}


class Checker:
    def __init__(self):
        self.failures = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        status = "PASS" if ok else "FAIL"
        if not ok:
            self.failures += 1
        suffix = f"  ({detail})" if detail and not ok else ""
        print(f"  [{status}] {name}{suffix}")


def load_tables() -> dict[str, pd.DataFrame]:
    tables = {}
    for name in SCHEMAS:
        path = config.DATA_DIR / f"{name}.parquet"
        if not path.exists():
            raise SystemExit(f"Missing {path}; run the pipeline first (make all).")
        tables[name] = pd.read_parquet(path)
    return tables


def run_checks(t: dict[str, pd.DataFrame]) -> Checker:
    c = Checker()

    print("Schemas (exact columns, in contract order):")
    for name, cols in SCHEMAS.items():
        actual = list(t[name].columns)
        c.check(f"{name} schema", actual == cols, f"got {actual}")

    commits, reviews = t["commits_clean"], t["reviews"]
    coupling, scored = t["coupling"], t["scored"]
    own_f, own_a = t["ownership_file"], t["ownership_author"]

    print("commits_clean:")
    c.check("dates are UTC datetimes", str(commits["date"].dtype) == "datetime64[ns, UTC]")
    c.check("additions/deletions are non-negative ints",
            bool((commits["additions"] >= 0).all() and (commits["deletions"] >= 0).all()))
    # Test the producers' real predicates on the distinct values, not a copy
    # of the rules that could drift from extract_commits.
    identities = commits[["author_canonical", "author_email_raw"]].drop_duplicates()
    n_bots = int(sum(is_bot(n, e) for n, e in identities.itertuples(index=False)))
    c.check("no bot authors slipped through (is_bot)", n_bots == 0, f"{n_bots} identities")
    paths = commits["file_path"].drop_duplicates()
    n_excl = int(sum(is_excluded(p) for p in paths))
    c.check("no excluded/vendored paths (is_excluded)", n_excl == 0, f"{n_excl} paths")

    print("ownership_file:")
    share_sums = own_f.groupby("file_path")["blame_share"].sum()
    c.check("blame_share sums to 1 per file",
            bool(np.allclose(share_sums, 1.0, atol=1e-6)),
            f"worst {share_sums.sub(1).abs().max():.2e}")
    leaders = own_f.groupby("file_path")["is_blame_leader"].sum()
    c.check("exactly one blame leader per file", bool((leaders == 1).all()),
            f"{int((leaders != 1).sum())} files off")
    majors = own_f.groupby("file_path")["is_major_owner"].sum()
    orphan = own_f.groupby("file_path")["is_orphan_risk"].first()
    c.check("orphan-risk == exactly one major owner",
            bool(((majors == 1) == orphan).all()))

    print("ownership_author:")
    surv = own_a["code_survival_tenure_normalized"]
    c.check("survival >= 0 or NaN", bool((surv.dropna() >= 0).all()))
    c.check("bus-factor flag matches file table",
            set(own_a.loc[own_a["bus_factor_flag"], "author_canonical"])
            == set(own_f.loc[own_f["is_major_owner"] & own_f["is_orphan_risk"],
                             "author_canonical"]))

    print("coupling:")
    c.check("centrality mass sums to ~1 (PageRank)",
            bool(abs(coupling["centrality_score"].sum() - 1.0) < 1e-6),
            f"sum {coupling['centrality_score'].sum():.6f}")
    c.check("no duplicate files", not coupling["file_path"].duplicated().any())

    print("reviews:")
    c.check("status values valid", bool(reviews["status"].isin(["complete", "partial"]).all()))
    c.check("approval_rate in [0,1]",
            bool(reviews["approval_rate"].between(0, 1).all()))
    c.check("distinct_authors_reviewed <= review_count",
            bool((reviews["distinct_authors_reviewed"] <= reviews["review_count"]).all()))

    print("scored:")
    components = scored[[
        "ownership_concentration", "code_survival_tenure_normalized",
        "coupling_criticality", "review_leverage",
    ]]
    c.check("impact_score == 0.25 * sum(components)",
            bool(np.allclose(scored["impact_score"], 0.25 * components.sum(axis=1))))
    c.check("components are percentiles in (0,1]",
            bool(((components > 0) & (components <= 1)).all().all()))
    c.check("sorted by impact_score descending",
            bool(scored["impact_score"].is_monotonic_decreasing))
    c.check("tiers start at 1 and never skip",
            bool(scored["tier"].iloc[0] == 1 and (scored["tier"].diff().dropna()
                                                  .isin([0, 1])).all()))
    c.check("imputed implies no review data",
            bool((~scored["review_data_imputed"] | ~scored["has_review_data"]).all()))
    universe = set(commits.loc[~commits["is_merge"], "author_canonical"])
    c.check("scored universe == non-merge commit authors",
            set(scored["author_canonical"]) == universe,
            f"{len(set(scored['author_canonical']) ^ universe)} mismatched")
    c.check("rationales filled (run narrate)",
            bool(scored["one_line_rationale"].str.len().gt(0).all()))

    return c


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate all pipeline outputs.")
    ap.parse_args()
    checker = run_checks(load_tables())
    if checker.failures:
        print(f"\n{checker.failures} check(s) FAILED")
        raise SystemExit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
