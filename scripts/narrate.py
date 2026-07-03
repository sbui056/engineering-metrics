"""Fill one_line_rationale in data/scored.parquet — deterministic, no LLM.

Each rationale names the author's strongest one or two signals in plain
language with a percentile qualifier, then appends the caveats that keep the
score honest: the bus-factor flag (ownership concentration is dual-use) and
the no-review-data badge (median-imputed, not observed). Rationales are pure
functions of the scored row, so reruns are reproducible.

Usage: python scripts/narrate.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

# (column, phrase) in the order used to break percentile ties.
SIGNAL_PHRASES = [
    ("ownership_concentration", "concentrated ownership of surviving code"),
    ("coupling_criticality", "ownership of files central to co-change"),
    ("code_survival_tenure_normalized", "code that outlasts tenure norms"),
    ("review_leverage", "review reach across contributors"),
]


def qualifier(p: float) -> str:
    if p >= 0.90:
        return "top-decile"
    if p >= 0.75:
        return "top-quartile"
    if p >= 0.50:
        return "above-median"
    return "below-median"


def rationale(row: pd.Series) -> str:
    """One sentence: strongest signal(s) above the median, plus honesty flags."""
    candidates = [
        (float(row[col]), i, phrase)
        for i, (col, phrase) in enumerate(SIGNAL_PHRASES)
        # An imputed review signal is a data gap, not evidence — never lead with it.
        if not (col == "review_leverage" and row["review_data_imputed"])
    ]
    strong = sorted(
        [c for c in candidates if c[0] >= 0.5], key=lambda c: (-c[0], c[1])
    )[:2]
    if strong:
        lead = " and ".join(f"{qualifier(p)} {phrase}" for p, _, phrase in strong)
    else:
        lead = "no signal above the repo median"

    flags = []
    if row["bus_factor_flag"]:
        flags.append("sole major owner of some files (bus-factor risk)")
    if row["review_data_imputed"]:
        flags.append("no review data (median-imputed)")
    tail = f" — {'; '.join(flags)}" if flags else ""
    return f"{lead[0].upper()}{lead[1:]}{tail}."


def build_rationales(df: pd.DataFrame) -> pd.Series:
    return df.apply(rationale, axis=1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fill one_line_rationale in scored.parquet.")
    ap.parse_args()

    path = config.DATA_DIR / "scored.parquet"
    df = pd.read_parquet(path)
    df["one_line_rationale"] = build_rationales(df)
    df.to_parquet(path, index=False)

    print(f"Wrote rationales for {len(df)} authors into {path}")
    for _, r in df.head(5).iterrows():
        print(f"  {r.author_canonical}: {r.one_line_rationale}")


if __name__ == "__main__":
    main()
